# Clip-Watcher Clipper

Keyword in, ranked Twitch highlights out. Finished YouTube uploads are coming next. See [PLAN.md](PLAN.md).

## Phase 1: rank clips for a keyword

```bash
pip install -r requirements.txt          # also needs ffmpeg on PATH
cp config.example.yaml config.yaml       # add Twitch client id/secret
export ANTHROPIC_API_KEY=...
python -m clipper rank --keyword valorant
python -m clipper rank --keyword valorant --no-ai   # skip Claude
```

Output: `data/reports/<keyword>-<time>.json` (ranked + dropped clips with reasons),
clip files in `data/clips/<keyword>/`, and word timestamps (`*.words.json`) for captions.

Tests: `python -m pytest -q`
