# Clip-Watcher Clipper: Plan

Give it a keyword. It finds the best Twitch moments, ranks them, edits them into
engaging videos (with AI voiceover and royalty-free sound effects/music) and
publishes them to YouTube. It runs fully automatically on a schedule.

## Decisions

| Topic | Decision |
|---|---|
| Automation | Fully automatic; automated safety filters replace a human review step |
| Voiceover | AI TTS, only where it helps: intro hook, countdown transitions, context for clips that need it, outro |
| Audio | Royalty-free / CC0 SFX and music only (no licensed tracks) |
| Goal | Engagement and retention |
| Keyword | Twitch category (game) first; title search as a fallback |
| Output | Weekly "Top 10" long-form + daily Shorts (configurable) |

## Pipeline

```
keyword -> 1 Discover -> 2 Moments -> 3 Fetch -> 4 Analyze -> 5 Rank
        -> 6 Edit (+VO, SFX, music) -> 7 Package -> 8 Publish -> 9 Track
```

1. **Discover**: keyword -> Twitch category -> top clips in the time window (Helix `clips`).
2. **Moments**: for allow-listed streamers, scan recent VODs: chat replay -> spike detection.
   This also covers streams that have already ended.
3. **Fetch**: `yt-dlp` downloads only the clip or segment, never the whole VOD.
4. **Analyze**: Whisper transcript (word timestamps) + ffmpeg loudness (peak vs. median).
5. **Rank**: views/spike strength + loudness + Claude judgement (standalone, entertainment,
   hook, safety). Overlapping moments are deduplicated. Unsafe clips are dropped.
6. **Edit**
   - Top 10: countdown 10 -> 1, #1 teaser in the first seconds, number cards, streamer credit.
   - Shorts: 9:16, word-by-word captions, hook text in the first second.
   - Engagement layer: zoom punch-in on loudness peaks, whoosh/impact SFX on transitions,
     background music ducked under speech, pattern interrupts every few seconds.
   - Voiceover: Claude writes short lines only where needed (hook, "Number 7...",
     context setup, CTA). TTS: Kokoro (local, free) by default; ElevenLabs optional.
7. **Package**: Claude writes the title, description (credits + chapters), tags and a
   comment-bait question; Pillow builds the thumbnail.
8. **Publish**: YouTube Data API upload + scheduled publish time; pinned comment.
9. **Track**: SQLite (used clips, uploads); later, analytics feed back into ranking weights.

## Automated safeguards (needed because nothing is reviewed by hand)

- Streamer allowlist (only creators who permit clipping), with credit in the video and description.
- Claude safety flag (slurs, NSFW, harassment) -> clip dropped.
- Music detection (the transcript says "[Music]" or there is a long non-speech stretch with high loudness) -> clip dropped.
- Duplicate guard via the DB; daily upload cap within the API quota (about 6/day).
- Kill switch: `enabled: false` in the config.

## Accounts / keys

| Item | Notes |
|---|---|
| Twitch app (client id/secret) | dev.twitch.tv, free |
| Google Cloud + YouTube Data API OAuth | uploads stay private until the API audit passes |
| Anthropic API key | ranking, voiceover script, metadata |
| CC0 audio pack in `assets/sfx`, `assets/music` | e.g. Freesound CC0, YouTube Audio Library |
| Server (VPS or PC) with ffmpeg | CPU is fine; only short clips get transcribed |

## Phases

1. **Keyword -> ranked clips** (this commit): discovery, fetch, analyze, score, dedupe, report.
2. Editing engine: Top 10 + Shorts, captions, SFX, music, zooms.
3. Voiceover + packaging (titles, thumbnails).
4. YouTube publishing + scheduler + DB guards.
5. VOD chat-spike mining at scale, analytics feedback loop.
