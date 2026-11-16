"""Deduplication, Claude judgement and final ranking."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .models import Candidate


# --- dedupe -----------------------------------------------------------------
def _overlap(a: tuple[str, float, float], b: tuple[str, float, float]) -> bool:
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


def _ts(s: str) -> float | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def dedupe(cands: list[Candidate], same_moment_seconds: float = 90) -> list[Candidate]:
    """Many viewers clip the same moment. Keep the best one per moment.

    Same moment = overlapping range in the same VOD, or (when the VOD is gone)
    same streamer and clip created within `same_moment_seconds`.
    """
    def strength(c: Candidate) -> float:
        return c.views + c.spike_strength * 1000

    kept: list[Candidate] = []
    for c in sorted(cands, key=strength, reverse=True):
        dup = False
        for k in kept:
            if c.vod_range and k.vod_range and _overlap(c.vod_range, k.vod_range):
                dup = True
            elif c.broadcaster and c.broadcaster.lower() == k.broadcaster.lower():
                tc, tk = _ts(c.created_at), _ts(k.created_at)
                if tc and tk and abs(tc - tk) <= same_moment_seconds and not (c.vod_range and k.vod_range):
                    dup = True
            if dup:
                break
        if not dup:
            kept.append(c)
    return kept


# --- Claude judgement ----------------------------------------------------------
class ClipVerdict(BaseModel):
    entertainment: int = Field(description="0-10: how funny, shocking, impressive or emotional")
    standalone: int = Field(description="0-10: makes sense to someone who never saw the stream")
    hook: int = Field(description="0-10: strength of the first 3 seconds")
    needs_context: bool = Field(description="True if a one-line voiceover setup would help a new viewer")
    context_line: str = Field(description="If needs_context, a <=15-word voiceover setup line, else empty")
    safety: Literal["ok", "drop"] = Field(
        description="drop for slurs, hate, sexual content, doxxing, self-harm, or copyrighted music as the main audio"
    )
    safety_reason: str
    summary: str = Field(description="One line describing what happens")


JUDGE_SYSTEM = (
    "You rate Twitch clips for a YouTube highlights channel whose goal is viewer "
    "engagement and retention. You only see the transcript and metadata, so judge "
    "from what was said, the chat-reaction strength and the loudness signal. "
    "Be strict: most clips are average (4-6). Reserve 8+ for moments people would share."
)


def judge(c: Candidate, keyword: str, client, model: str, effort: str) -> dict:
    prompt = (
        f"Keyword / game: {keyword}\n"
        f"Streamer: {c.broadcaster}\n"
        f"Clip title (written by a viewer): {c.title!r}\n"
        f"Views: {c.views}   Chat spike strength: {c.spike_strength:.1f}x   "
        f"Loudness excitement: {c.loudness_excitement:.1f} LU\n"
        f"Duration: {c.duration:.0f}s\n\n"
        f"Transcript:\n{c.transcript or '(no speech detected)'}"
    )
    resp = client.beta.messages.parse(
        model=model,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort},
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=ClipVerdict,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return {"safety": "drop", "safety_reason": "model declined to rate", "entertainment": 0,
                "standalone": 0, "hook": 0, "needs_context": False, "context_line": "", "summary": ""}
    return resp.parsed_output.model_dump()


# --- final score -------------------------------------------------------------
def ai_score(ai: dict) -> float:
    if not ai:
        return 0.0
    return 0.5 * ai.get("entertainment", 0) + 0.3 * ai.get("standalone", 0) + 0.2 * ai.get("hook", 0)


def rank(cands: list[Candidate], weights: dict, min_ai_score: float, use_ai: bool = True) -> list[Candidate]:
    """Combine normalised signals into a 0-10 score. Mutates and returns kept candidates, best first."""
    if not cands:
        return []
    pop_raw = [math.log1p(c.views) + 2.0 * math.log1p(c.spike_strength) for c in cands]
    top_pop = max(pop_raw) or 1.0
    w_pop, w_audio, w_ai = weights.get("popularity", 0.35), weights.get("audio", 0.15), weights.get("ai", 0.5)
    if not use_ai:  # re-spread the AI weight when Claude is not used
        total = (w_pop + w_audio) or 1.0
        w_pop, w_audio, w_ai = w_pop / total, w_audio / total, 0.0

    kept = []
    for c, p in zip(cands, pop_raw):
        if use_ai:
            if c.ai.get("safety") == "drop":
                c.dropped_reason = f"safety: {c.ai.get('safety_reason', '')}"
                continue
            if ai_score(c.ai) < min_ai_score:
                c.dropped_reason = f"ai score {ai_score(c.ai):.1f} < {min_ai_score}"
                continue
        pop = 10 * p / top_pop
        audio = min(10.0, c.loudness_excitement)  # ~10 LU above median is already a big spike
        c.score = round(w_pop * pop + w_audio * audio + w_ai * ai_score(c.ai), 2)
        kept.append(c)
    return sorted(kept, key=lambda c: c.score, reverse=True)
