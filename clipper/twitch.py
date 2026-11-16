"""Minimal Twitch Helix client (app access token, no user login needed)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

from .models import Candidate

HELIX = "https://api.twitch.tv/helix"


class Twitch:
    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise ValueError("Twitch client_id/client_secret missing (see config.example.yaml)")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_exp = 0.0
        self.s = requests.Session()

    def _auth(self) -> dict:
        if not self._token or time.time() > self._token_exp - 60:
            r = requests.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=30,
            )
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._token_exp = time.time() + body.get("expires_in", 3600)
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {self._token}"}

    def get(self, path: str, **params) -> dict:
        for attempt in range(4):
            r = self.s.get(f"{HELIX}/{path}", headers=self._auth(), params=params, timeout=30)
            if r.status_code == 429:
                reset = float(r.headers.get("Ratelimit-Reset", time.time() + 2))
                time.sleep(max(1.0, reset - time.time()))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    def paginate(self, path: str, limit: int, **params):
        cursor = None
        n = 0
        while n < limit:
            p = dict(params, first=min(100, limit - n))
            if cursor:
                p["after"] = cursor
            body = self.get(path, **p)
            items = body.get("data", [])
            for it in items:
                yield it
                n += 1
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor or not items:
                return

    # --- lookups -----------------------------------------------------------
    def find_category(self, keyword: str) -> dict | None:
        results = self.get("search/categories", query=keyword, first=10).get("data", [])
        if not results:
            return None
        kw = keyword.lower().strip()
        for c in results:
            if c["name"].lower() == kw:
                return c
        if len(results) > 1:
            import logging
            logging.getLogger("clipper").warning(
                "no exact category match for %r; using %r (set `category:` in config to pin it)",
                keyword, results[0]["name"])
        return results[0]

    def users_by_login(self, logins: list[str]) -> dict[str, dict]:
        out = {}
        for i in range(0, len(logins), 100):
            chunk = logins[i : i + 100]
            body = self.get("users", login=chunk)
            for u in body.get("data", []):
                out[u["login"].lower()] = u
        return out

    # --- clips -------------------------------------------------------------
    def top_clips(
        self,
        *,
        game_id: str | None = None,
        broadcaster_id: str | None = None,
        days: int = 7,
        limit: int = 200,
    ) -> list[Candidate]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        params = {"started_at": _iso(start), "ended_at": _iso(end)}
        if game_id:
            params["game_id"] = game_id
        if broadcaster_id:
            params["broadcaster_id"] = broadcaster_id
        return [clip_to_candidate(c) for c in self.paginate("clips", limit, **params)]

    def recent_vods(self, user_id: str, days: int = 7, limit: int = 10) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        vods = []
        for v in self.paginate("videos", limit, user_id=user_id, type="archive"):
            created = datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
            if created >= cutoff:
                vods.append(v)
        return vods


def clip_to_candidate(c: dict) -> Candidate:
    return Candidate(
        id=f"clip:{c['id']}",
        source="clip",
        url=c["url"],
        broadcaster=c.get("broadcaster_name", ""),
        title=c.get("title", ""),
        created_at=c.get("created_at", ""),
        views=int(c.get("view_count", 0)),
        duration=float(c.get("duration", 30)),
        language=c.get("language", ""),
        video_id=c.get("video_id") or None,
        vod_offset=float(c["vod_offset"]) if c.get("vod_offset") is not None else None,
    )


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")
