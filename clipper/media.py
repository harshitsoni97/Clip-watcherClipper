"""Downloading (yt-dlp), loudness (ffmpeg) and transcription (faster-whisper)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from statistics import median

from .models import Candidate


def download(c: Candidate, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", c.id)
    out = out_dir / f"{safe}.mp4"
    if out.exists():
        return out
    cmd = ["yt-dlp", "-q", "--no-warnings", "-f", "best[ext=mp4]/best", "-o", str(out)]
    if c.source == "vod_spike":
        start, end = c.vod_offset or 0.0, (c.vod_offset or 0.0) + c.duration
        cmd += ["--download-sections", f"*{start:.0f}-{end:.0f}", "--force-keyframes-at-cuts"]
    cmd.append(c.url)
    subprocess.run(cmd, check=True)
    return out


def loudness_excitement(path: Path) -> float:
    """How much louder the loudest moment is than the clip's typical level (LU).

    Screams, laughter and big reactions give large values. Uses ffmpeg's ebur128
    momentary loudness (M:) readings, ten per second.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    vals = [float(v) for v in re.findall(r"\bM:\s*(-?\d+(?:\.\d+)?)", proc.stderr)]
    vals = [v for v in vals if v > -70]  # ignore digital silence
    if len(vals) < 10:
        return 0.0
    vals.sort()
    p95 = vals[int(len(vals) * 0.95) - 1]
    return max(0.0, p95 - median(vals))


_whisper_model = None


def transcribe(path: Path, model_name: str = "small", device: str = "cpu") -> tuple[str, list[dict]]:
    """Return (full_text, words[{start,end,word}]). Words feed caption rendering later."""
    global _whisper_model
    from faster_whisper import WhisperModel

    if _whisper_model is None:
        compute = "int8" if device == "cpu" else "float16"
        _whisper_model = WhisperModel(model_name, device=device, compute_type=compute)
    segments, _ = _whisper_model.transcribe(str(path), word_timestamps=True, vad_filter=True)
    words, parts = [], []
    for seg in segments:
        parts.append(seg.text.strip())
        for w in seg.words or []:
            words.append({"start": w.start, "end": w.end, "word": w.word})
    return " ".join(parts).strip(), words
