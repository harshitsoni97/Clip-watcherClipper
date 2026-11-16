"""SQLite memory: which moments were already used, so nothing is posted twice."""
from __future__ import annotations

import sqlite3
from pathlib import Path


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS used_clips ("
            " id TEXT PRIMARY KEY, keyword TEXT, video_id TEXT, start REAL, end REAL,"
            " used_in TEXT, used_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self.conn.commit()

    def is_used(self, cand) -> bool:
        if self.conn.execute("SELECT 1 FROM used_clips WHERE id=?", (cand.id,)).fetchone():
            return True
        if cand.vod_range:
            vid, s, e = cand.vod_range
            row = self.conn.execute(
                "SELECT 1 FROM used_clips WHERE video_id=? AND start<? AND end>?", (vid, e, s)
            ).fetchone()
            return row is not None
        return False

    def mark_used(self, cand, keyword: str, used_in: str) -> None:
        vid, s, e = cand.vod_range or (None, None, None)
        self.conn.execute(
            "INSERT OR REPLACE INTO used_clips (id, keyword, video_id, start, end, used_in)"
            " VALUES (?,?,?,?,?,?)",
            (cand.id, keyword, vid, s, e, used_in),
        )
        self.conn.commit()
