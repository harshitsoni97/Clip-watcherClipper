from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_config(path: str | Path = "config.yaml") -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    tw = cfg.setdefault("twitch", {})
    tw["client_id"] = os.environ.get("TWITCH_CLIENT_ID", tw.get("client_id", ""))
    tw["client_secret"] = os.environ.get("TWITCH_CLIENT_SECRET", tw.get("client_secret", ""))
    cfg.setdefault("data_dir", "data")
    cfg.setdefault("scoring", {}).setdefault(
        "weights", {"popularity": 0.35, "audio": 0.15, "ai": 0.5}
    )
    cfg["scoring"].setdefault("min_ai_score", 5)
    cfg.setdefault("chat_spikes", {})
    cfg.setdefault("claude", {}).setdefault("model", "claude-opus-5-5")
    cfg["claude"].setdefault("effort", "medium")
    cfg.setdefault("whisper", {}).setdefault("model", "small")
    cfg["whisper"].setdefault("device", "cpu")
    return cfg
