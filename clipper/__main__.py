"""Usage:
    python -m clipper rank                      # run every job in config.yaml
    python -m clipper rank --keyword valorant   # one keyword (uses the first job's settings)
    python -m clipper rank --no-ai              # skip Claude (popularity + loudness only)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import load_config
from .pipeline import run_job


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="clipper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rank", help="keyword -> ranked clips report")
    r.add_argument("--config", default="config.yaml")
    r.add_argument("--keyword")
    r.add_argument("--no-ai", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    if not cfg.get("enabled", True):
        print("disabled in config (enabled: false)")
        return 0

    jobs = cfg.get("jobs") or [{}]
    if args.keyword:
        jobs = [dict(jobs[0], keyword=args.keyword)]
    for job in jobs:
        report = run_job(cfg, job, use_ai=not args.no_ai)
        data = json.loads(report.read_text())
        print(f"\n== {job['keyword']}: {len(data['ranked'])} ranked, {len(data['dropped'])} dropped -> {report}")
        for i, c in enumerate(data["ranked"][:10], 1):
            print(f"{i:>2}. {c['score']:>5}  {c['broadcaster']:<18} {c['views']:>7} views  {c['title'][:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
