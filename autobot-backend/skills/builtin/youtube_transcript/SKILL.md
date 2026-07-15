---
name: youtube-transcript
version: 1.0.0
description: Extract timestamped transcripts and metadata from YouTube videos using yt-dlp
author: mrveiss
category: internet
tools:
  - get_transcript
  - get_metadata
  - search_videos
triggers:
  - youtube transcript
  - video transcript
  - get subtitles
  - what does this video say
  - summarize YouTube video
  - extract captions
  - YouTube URL
  - watch video
  - yt-dlp
tags:
  - youtube
  - transcript
  - captions
  - subtitles
  - video
  - yt-dlp
  - media
---

## Capability Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ youtube-transcript                                            │
├─────────────────────────────────────────────────────────────┤
│ STANDALONE   (always works, zero config)                     │
│   • Extract auto/manual captions + metadata for any public   │
│     video via yt-dlp (no login, no video download)           │
├─────────────────────────────────────────────────────────────┤
│ SUPERCHARGED (unlocks when you connect a tool)               │
│   • Browser cookies (--cookies-from-browser) → age-gated,    │
│     members-only, and private videos you can access          │
└─────────────────────────────────────────────────────────────┘
```

**STANDALONE — always works, zero config**

- Download manual or auto-generated captions for any public video with `yt-dlp`
  (subtitles only — the video itself is never downloaded).
- Fetch full video metadata (`--dump-json`) and search YouTube for video IDs.
- Graceful degradation: manual subs → auto-generated subs → description text.

**SUPERCHARGED — unlocks per connected tool**

| Connect this | Unlocks |
|--------------|---------|
| Browser cookies (`--cookies-from-browser firefox`) | Transcripts and metadata for age-gated, members-only, or private videos that the signed-in browser session can access. |

Without cookies the skill simply stays on the public-video STANDALONE tier.

## Output Contract

Transcript extraction returns this fixed shape:

```
## Transcript: <video title>

**Video:** <url or id>   **Duration:** <hh:mm:ss>   **Uploader:** <name>
**Caption source:** manual | auto-generated | description-fallback

<plain-text transcript, timing tags stripped>
```

Metadata-only requests return the raw `--dump-json` object (keys: `title`,
`description`, `duration`, `uploader`, `view_count`, `upload_date`, `chapters`).

## When to Use

Use this skill when an agent needs to read or summarize the spoken content of a
YouTube video. yt-dlp downloads subtitle/caption files without downloading the
video itself, making transcript extraction fast and bandwidth-efficient.

## Workflow

### Primary path — auto-generated English captions

```bash
# Download auto-generated English subtitles as VTT (no video download)
yt-dlp --write-auto-sub --sub-lang en --skip-download '{youtube_url}'
# Output file: <video_title>.en.vtt in current directory
```

Steps:
1. Run the yt-dlp command with the target YouTube URL.
2. Locate the generated `.vtt` file.
3. Strip VTT timing tags to obtain plain text:
   ```bash
   grep -v '^WEBVTT\|^[0-9]\|^$\|-->' <file>.vtt | sort -u
   ```
4. Pass the plain text to the LLM context for summarization or Q&A.

### Manual subtitles (preferred when available)

```bash
# Download manually uploaded English subtitles as SRT
yt-dlp --write-sub --sub-lang en --sub-format srt --skip-download '{youtube_url}'
```

### Video metadata only (no transcript needed)

```bash
yt-dlp --dump-json --no-download '{youtube_url}'
```

Returns JSON with `title`, `description`, `duration`, `uploader`,
`view_count`, `upload_date`, and `chapters`.

### Search YouTube for video IDs

```bash
yt-dlp 'ytsearch{count}:{query}' --get-id
# Example: yt-dlp 'ytsearch5:python asyncio tutorial' --get-id
```

## Output Format

- **Transcript (VTT):** Timestamped caption blocks. Strip timing lines to get
  plain text paragraphs.
- **Transcript (SRT):** Numbered subtitle entries with start/end timestamps.
- **Metadata (JSON):** Full video metadata object; use `jq` to extract specific
  fields (e.g., `jq '.title'`).

## Parameters

| Parameter    | Type   | Required | Description                                |
|--------------|--------|----------|--------------------------------------------|
| youtube_url  | string | yes      | Full YouTube video URL or video ID         |
| language     | string | no       | BCP-47 language code, default `en`         |
| format       | string | no       | `vtt` (default) or `srt`                   |

## Limitations

- Auto-generated captions may have transcription errors, especially for
  technical jargon, accents, or non-English speech.
- Some videos disable captions entirely; no fallback transcript is available.
- Age-gated or private videos require cookies (`--cookies-from-browser firefox`).
- yt-dlp extractors may break after YouTube updates; run `yt-dlp -U` to
  self-update before retrying.
- Does not support live streams (use `--live-from-start` for ongoing streams).

## Fallback Instructions

If yt-dlp reports no subtitles available:
1. Try `--write-auto-sub` in case only auto-generated captions exist.
2. If still empty, fetch the video description via `--dump-json` and summarize
   the description as a proxy for content.
3. If the video is inaccessible, report the URL as unavailable and ask the user
   to paste the transcript manually or provide an alternative source.
