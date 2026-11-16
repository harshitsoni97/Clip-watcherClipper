import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipper import chat, score  # noqa: E402
from clipper.db import DB  # noqa: E402
from clipper.models import Candidate  # noqa: E402


def make_chat(spike_at: float, length: float = 1200):
    random.seed(1)
    msgs = []
    t = 0.0
    while t < length:  # quiet background: ~1 msg/s from a pool of 40 chatters
        msgs.append((t, f"user{random.randint(0, 40)}", "hello"))
        t += 1.0
    for i in range(80):  # 80 different people reacting within 10s
        msgs.append((spike_at + i * 0.1, f"hype{i}", "KEKW clip it"))
    return msgs


def test_spike_detected_with_lead():
    scores = chat.bucket_scores(make_chat(600), bucket=10)
    spikes = chat.find_spikes(scores, bucket=10, lead_seconds=20, tail_seconds=10)
    assert len(spikes) == 1
    s = spikes[0]
    assert s["peak"] == 600
    assert s["start"] == 580 and s["end"] == 620
    assert s["strength"] > 5


def test_spammer_cannot_fake_spike():
    msgs = [(t * 1.0, f"u{t % 30}", "hi") for t in range(600)]
    msgs += [(300 + i * 0.05, "spammer", "KEKW KEKW clip it") for i in range(200)]
    spikes = chat.find_spikes(chat.bucket_scores(msgs, 10), bucket=10)
    assert spikes == []


def test_emoji_weight():
    assert chat.message_weight("💀💀") == 1.0
    assert chat.message_weight("clip it") == 3.0
    assert chat.message_weight("hello there") == 0.0


def _clip(i, views, vid=None, off=None, who="A", created="2026-11-10T10:00:00Z"):
    return Candidate(id=f"clip:{i}", source="clip", url="u", broadcaster=who, title=f"t{i}",
                     views=views, video_id=vid, vod_offset=off, duration=30, created_at=created)


def test_dedupe_overlapping_vod_ranges_keeps_most_viewed():
    a = _clip(1, 100, "v1", 1000)
    b = _clip(2, 900, "v1", 1010)
    c = _clip(3, 50, "v1", 5000)
    kept = score.dedupe([a, b, c])
    assert [k.id for k in kept] == ["clip:2", "clip:3"]


def test_dedupe_without_vod_uses_time_window():
    a = _clip(1, 100, created="2026-11-10T10:00:00Z")
    b = _clip(2, 300, created="2026-11-10T10:00:40Z")
    c = _clip(3, 50, created="2026-11-10T12:00:00Z")
    assert [k.id for k in score.dedupe([a, b, c])] == ["clip:2", "clip:3"]


def test_rank_drops_unsafe_and_low_quality():
    good = _clip(1, 1000); good.ai = dict(entertainment=9, standalone=8, hook=8, safety="ok")
    meh = _clip(2, 5000); meh.ai = dict(entertainment=3, standalone=3, hook=2, safety="ok")
    bad = _clip(3, 9000); bad.ai = dict(entertainment=10, standalone=10, hook=10, safety="drop", safety_reason="slur")
    ranked = score.rank([good, meh, bad], {"popularity": 0.35, "audio": 0.15, "ai": 0.5}, 5)
    assert [c.id for c in ranked] == ["clip:1"]
    assert "safety" in bad.dropped_reason and "ai score" in meh.dropped_reason


def test_rank_without_ai_orders_by_popularity_and_audio():
    a = _clip(1, 10); b = _clip(2, 10000)
    ranked = score.rank([a, b], {"popularity": 0.35, "audio": 0.15, "ai": 0.5}, 5, use_ai=False)
    assert [c.id for c in ranked] == ["clip:2", "clip:1"]
    assert ranked[0].score == 7.0  # 0.7 popularity weight * 10, no audio


def test_db_blocks_reuse_of_overlapping_moment(tmp_path):
    db = DB(tmp_path / "x.db")
    db.mark_used(_clip(1, 10, "v9", 100), "kw", "top10-1")
    assert db.is_used(_clip(2, 10, "v9", 120))
    assert not db.is_used(_clip(3, 10, "v9", 500))
