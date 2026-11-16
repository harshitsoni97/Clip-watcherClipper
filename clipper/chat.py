"""Chat-spike detection on VOD chat replays (works after the stream has ended)."""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import median
from typing import Iterable

# Reactions that signal "something just happened". Weighted on top of unique chatters.
HYPE_PATTERNS = {
    r"\b(kekw|omegalul|lul|lmao+|lmfao|xd+|haha+|ahah+|icant)\b|💀|😂": 1.0,
    r"\b(pog|pogchamp|poggers|pogu|w+|insane|no ?way|holy|wtf|omg)\b": 1.0,
    r"\bclip (it|that)\b|\bclipped\b": 3.0,
}
_COMPILED = [(re.compile(p, re.I), w) for p, w in HYPE_PATTERNS.items()]


def message_weight(text: str) -> float:
    return sum(w for rx, w in _COMPILED if rx.search(text))


def bucket_scores(messages: Iterable[tuple[float, str, str]], bucket: float = 10.0) -> dict[int, float]:
    """messages: (seconds_into_vod, author, text). Returns bucket index -> score.

    score = unique chatters + reaction weight (each author counted once per bucket,
    so one spammer cannot fake a spike).
    """
    authors: dict[int, set] = defaultdict(set)
    hype: dict[int, dict[str, float]] = defaultdict(dict)
    for t, author, text in messages:
        b = int(t // bucket)
        authors[b].add(author)
        w = message_weight(text)
        if w:
            hype[b][author] = max(hype[b].get(author, 0.0), w)
    return {b: len(a) + sum(hype[b].values()) for b, a in authors.items()}


def find_spikes(
    scores: dict[int, float],
    *,
    bucket: float = 10.0,
    baseline_buckets: int = 30,
    multiplier: float = 2.5,
    min_score: float = 15.0,
    lead_seconds: float = 20.0,
    tail_seconds: float = 10.0,
) -> list[dict]:
    """Return merged moments: {start, end, peak, strength}."""
    if not scores:
        return []
    last = max(scores)
    series = [scores.get(i, 0.0) for i in range(last + 1)]
    raw = []
    for i, s in enumerate(series):
        window = series[max(0, i - baseline_buckets) : i]
        base = max(median(window) if window else 0.0, 1.0)
        if s >= min_score and s >= multiplier * base:
            peak_t = i * bucket
            raw.append({
                "start": max(0.0, peak_t - lead_seconds),
                "end": peak_t + bucket + tail_seconds,
                "peak": peak_t,
                "strength": s / base,
            })
    # merge overlapping windows, keep the strongest peak
    merged: list[dict] = []
    for m in raw:
        if merged and m["start"] <= merged[-1]["end"]:
            prev = merged[-1]
            prev["end"] = max(prev["end"], m["end"])
            if m["strength"] > prev["strength"]:
                prev["peak"], prev["strength"] = m["peak"], m["strength"]
        else:
            merged.append(dict(m))
    return merged


def fetch_vod_chat(vod_url: str):
    """Yield (seconds, author, text) from a Twitch/YouTube VOD chat replay."""
    from chat_downloader import ChatDownloader  # imported lazily: heavy dependency

    for msg in ChatDownloader().get_chat(vod_url):
        t = msg.get("time_in_seconds")
        if t is None:
            continue
        author = (msg.get("author") or {}).get("name", "?")
        yield float(t), author, msg.get("message") or ""
