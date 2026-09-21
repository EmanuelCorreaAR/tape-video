# Tape

**SQLite for long videos.**

Tape turns a long video into a small, local, queryable temporal index — then lets you clip and compress from that index.

```text
video.mp4  →  video.mp4.tape  →  SQL / detect / clips / digest
```

Not an editor. Not a cloud API. An **embedded timeline database** next to your file.

## Why

Long videos are mostly dead time. Most pipelines still upload and process everything.

Tape does the opposite:

1. **Index cheap signals locally** (motion, audio energy)
2. **Query the timeline** (SQL)
3. **Cut only what matters** (ffmpeg)

## Quickstart

Requirements:

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) on your `PATH` (`brew install ffmpeg`)

```bash
git clone https://github.com/EmanuelCorreaAR/tape.git
cd tape
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

tape index lecture.mp4
tape info lecture.mp4
tape sql lecture.mp4 "SELECT t0, t1, motion, audio_rms FROM timeline_bins WHERE motion > 0.3 LIMIT 20"
tape detect lecture.mp4
tape compress lecture.mp4 --out digest.mp4
```

Demo promise:

```bash
tape compress long.mp4 --out digest.mp4
# 2h → ~15–25m of active segments (depends on content + thresholds)
```

## Commands

| Command | What it does |
|---------|----------------|
| `tape index VIDEO` | Build `VIDEO.tape` (SQLite) with 1s motion/audio bins |
| `tape info TARGET` | Show duration, bins, segments |
| `tape sql TARGET "SELECT …"` | Query the index |
| `tape detect TARGET` | Write `activity` segments from bins |
| `tape segments TARGET` | List segments |
| `tape clip TARGET --out clips/` | Export segment clips |
| `tape compress TARGET --out digest.mp4` | Keep only activity → one digest |

`TARGET` can be the video or the `.tape` file.

## Schema (v0)

The `.tape` file is SQLite:

- `media` — path, duration, size, hash prefix
- `timeline_bins` — fixed grid (`motion`, `audio_rms`, `audio_onset`, `luma`)
- `segments` — derived intervals (`kind`, `start_s`, `end_s`, `score`, `source`)
- `meta` — `tape_version`, params

Inspect anything with:

```bash
sqlite3 lecture.mp4.tape ".schema"
```

## Design principles

1. **Local-first** — indexing runs on your machine
2. **Proxy ≠ original** — understand cheaply, cut from the source
3. **SQL is the interface** — the index is inspectable and portable
4. **Plugins later** — core stores signals; meaning (speech, sports, CCTV) plugs in
5. **Cheap by default** — CPU, ~1 fps sampling, no GPU required

## Non-goals (for now)

- Full NLE / timeline UI
- Cloud upload pipeline
- Mandatory ML models
- Replacing ffmpeg

## Status

**v0.1 alpha** — useful for experiments and demos. Schema may still evolve; `tape_version` is stored in `meta`.

## License

MIT
