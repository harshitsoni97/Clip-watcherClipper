from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Candidate:
    """One possible moment: either a viewer-made Twitch clip or a VOD chat spike."""

    id: str
    source: str  # "clip" | "vod_spike"
    url: str  # what yt-dlp downloads (clip URL or VOD URL)
    broadcaster: str
    title: str
    created_at: str = ""
    views: int = 0
    duration: float = 30.0
    language: str = ""
    video_id: Optional[str] = None  # parent VOD id, if known
    vod_offset: Optional[float] = None  # start of the moment inside the VOD (seconds)
    spike_strength: float = 0.0  # spike score / baseline, for VOD spikes

    # filled in by later stages
    file: Optional[str] = None
    transcript: str = ""
    loudness_excitement: float = 0.0
    ai: dict = field(default_factory=dict)
    score: float = 0.0
    dropped_reason: str = ""

    @property
    def vod_range(self) -> Optional[tuple[str, float, float]]:
        if self.video_id and self.vod_offset is not None:
            return (self.video_id, self.vod_offset, self.vod_offset + self.duration)
        return None
