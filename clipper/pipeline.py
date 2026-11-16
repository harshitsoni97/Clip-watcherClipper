"""Phase 1: keyword -> discovered moments -> analysed -> ranked report."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import chat, media, score
from .db import DB
from .models import Candidate
from .twitch import Twitch

log = logging.getLogger("clipper")


def discover(tw: Twitch, job: dict, spike_cfg: dict) -> list[Candidate]:
    keyword = job["keyword"]
    days = job.get("window_days", 7)
    langs = set(job.get("languages") or [])
    allow = [a.lower() for a in job.get("allowlist") or []]
    users = tw.users_by_login(allow) if allow else {}
    allow_ids = {u["id"] for u in users.values()}

    cands: list[Candidate] = []
    cat = tw.find_category(keyword)
    if cat:
        log.info("keyword %r -> category %s (%s)", keyword, cat["name"], cat["id"])
        cands += tw.top_clips(game_id=cat["id"], days=days, limit=300)
    # allow-listed streamers' own clips (catches moments outside the category, e.g. Just Chatting)
    for u in users.values():
        cands += tw.top_clips(broadcaster_id=u["id"], days=days, limit=100)
    if not cat and not users:
        log.warning("no category or allowlist for %r; nothing to search", keyword)

    # filters
    if allow_ids or allow:
        names = {u["display_name"].lower() for u in users.values()} | set(allow)
        cands = [c for c in cands if c.broadcaster.lower() in names]
    if langs:
        cands = [c for c in cands if not c.language or c.language.split("-")[0] in langs]
    if not cat:  # no category match: keep clips whose title mentions the keyword
        cands = [c for c in cands if keyword.lower() in c.title.lower()] or cands

    # VOD chat-spike mining (works after the stream ended)
    if job.get("vod_scan") and users:
        for u in users.values():
            for v in tw.recent_vods(u["id"], days=days, limit=5):
                cands += vod_spike_candidates(v, u["display_name"], spike_cfg)
    return cands


def vod_spike_candidates(vod: dict, broadcaster: str, spike_cfg: dict) -> list[Candidate]:
    url = vod["url"]
    bucket = spike_cfg.get("bucket_seconds", 10)
    try:
        scores = chat.bucket_scores(chat.fetch_vod_chat(url), bucket=bucket)
    except Exception as e:  # sub-only, expired or chat unavailable
        log.warning("chat replay failed for %s: %s", url, e)
        return []
    spikes = chat.find_spikes(
        scores,
        bucket=bucket,
        baseline_buckets=spike_cfg.get("baseline_buckets", 30),
        multiplier=spike_cfg.get("multiplier", 2.5),
        min_score=spike_cfg.get("min_score", 15),
        lead_seconds=spike_cfg.get("lead_seconds", 20),
        tail_seconds=spike_cfg.get("tail_seconds", 10),
    )
    log.info("%s: %d chat spikes", url, len(spikes))
    return [
        Candidate(
            id=f"vod:{vod['id']}:{int(s['start'])}",
            source="vod_spike",
            url=url,
            broadcaster=broadcaster,
            title=vod.get("title", ""),
            created_at=vod.get("created_at", ""),
            duration=min(60.0, s["end"] - s["start"]),
            language=vod.get("language", ""),
            video_id=vod["id"],
            vod_offset=s["start"],
            spike_strength=s["strength"],
        )
        for s in spikes
    ]


def run_job(cfg: dict, job: dict, *, use_ai: bool = True) -> Path:
    data = Path(cfg["data_dir"])
    keyword = job["keyword"]
    db = DB(data / "clipper.db")
    tw = Twitch(cfg["twitch"]["client_id"], cfg["twitch"]["client_secret"])

    cands = discover(tw, job, cfg["chat_spikes"])
    log.info("discovered %d candidates", len(cands))
    cands = [c for c in score.dedupe(cands) if not db.is_used(c)]
    # cheap pre-rank by popularity so we only download/transcribe the most promising
    cands.sort(key=lambda c: c.views + c.spike_strength * 1000, reverse=True)
    cands = cands[: job.get("max_candidates", 40)]
    log.info("analysing %d candidates", len(cands))

    client = None
    if use_ai:
        import anthropic

        client = anthropic.Anthropic()

    analysed = []
    for c in cands:
        try:
            path = media.download(c, data / "clips" / keyword)
            c.file = str(path)
            c.loudness_excitement = media.loudness_excitement(path)
            c.transcript, words = media.transcribe(path, cfg["whisper"]["model"], cfg["whisper"]["device"])
            path.with_suffix(".words.json").write_text(json.dumps(words))
            if client:
                c.ai = score.judge(c, keyword, client, cfg["claude"]["model"], cfg["claude"]["effort"])
            analysed.append(c)
        except Exception as e:
            log.warning("skipping %s: %s", c.id, e)

    ranked = score.rank(analysed, cfg["scoring"]["weights"], cfg["scoring"]["min_ai_score"], use_ai=use_ai)
    dropped = [c for c in analysed if c.dropped_reason]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = data / "reports" / f"{keyword}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "keyword": keyword,
        "generated_at": stamp,
        "ranked": [asdict(c) for c in ranked],
        "dropped": [asdict(c) for c in dropped],
    }, indent=2))
    return out
