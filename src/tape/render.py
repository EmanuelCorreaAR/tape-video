"""Cut clips and build condensed digests with ffmpeg."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from tape.db import connect, require_media, tape_path_for
from tape.detect import detect_activity, list_segments
from tape.ffmpeg_util import ffmpeg_bin, run

console = Console()


def resolve_db(video_or_db: Path) -> tuple[Path, Path]:
    """Return (video_path, db_path)."""
    p = video_or_db.resolve()
    if p.suffix == ".tape" or str(p).endswith(".tape"):
        conn = connect(p)
        media = require_media(conn)
        video = Path(media["abs_path"])
        conn.close()
        return video, p
    db = tape_path_for(p)
    if not db.exists():
        raise SystemExit(f"Missing index: {db}. Run `tape index {p}` first.")
    return p, db


def clip_range(video: Path, start_s: float, end_s: float, out: Path, *, reencode: bool = False) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.01, end_s - start_s)
    if reencode:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            f"{start_s:.3f}",
            "-i",
            str(video),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(out),
        ]
    else:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            f"{start_s:.3f}",
            "-i",
            str(video),
            "-t",
            f"{duration:.3f}",
            "-c",
            "copy",
            str(out),
        ]
    result = run(cmd, check=False)
    if result.returncode != 0 or not out.exists():
        # fallback reencode
        if not reencode:
            return clip_range(video, start_s, end_s, out, reencode=True)
        raise SystemExit(result.stderr[-2000:] if result.stderr else "ffmpeg clip failed")
    return out


def export_segments(
    video_or_db: Path,
    out_dir: Path,
    *,
    kind: str = "activity",
    limit: int | None = None,
) -> list[Path]:
    video, db = resolve_db(video_or_db)
    segs = list_segments(db, kind=kind)
    if not segs:
        detect_activity(db)
        segs = list_segments(db, kind=kind)
    if limit is not None:
        segs = sorted(segs, key=lambda r: float(r["score"] or 0), reverse=True)[:limit]
        segs = sorted(segs, key=lambda r: float(r["start_s"]))

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, seg in enumerate(segs, start=1):
        start = float(seg["start_s"])
        end = float(seg["end_s"])
        out = out_dir / f"{kind}_{i:03d}_{start:.1f}-{end:.1f}.mp4"
        clip_range(video, start, end, out)
        paths.append(out)
        console.print(f"[green]clip[/green] {out.name}")
    return paths


def compress(
    video_or_db: Path,
    out: Path,
    *,
    kind: str = "activity",
    motion_thresh: float = 0.12,
    audio_thresh: float = 0.18,
) -> Path:
    video, db = resolve_db(video_or_db)
    detect_activity(db, motion_thresh=motion_thresh, audio_thresh=audio_thresh)
    segs = list_segments(db, kind=kind)
    if not segs:
        raise SystemExit("No activity segments found. Try lowering thresholds.")

    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f".tape_compress_{out.stem}"
    work.mkdir(exist_ok=True)
    parts: list[Path] = []
    for i, seg in enumerate(segs, start=1):
        part = work / f"part_{i:04d}.mp4"
        clip_range(video, float(seg["start_s"]), float(seg["end_s"]), part)
        parts.append(part)

    concat_list = work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts),
        encoding="utf-8",
    )
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(out),
    ]
    result = run(cmd, check=False)
    if result.returncode != 0:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            str(out),
        ]
        run(cmd)

    # cleanup parts
    for p in parts:
        p.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)
    try:
        work.rmdir()
    except OSError:
        pass

    kept = sum(float(s["end_s"]) - float(s["start_s"]) for s in segs)
    conn = connect(db)
    media = require_media(conn)
    original = float(media["duration_s"])
    conn.close()

    meta = {
        "original_s": original,
        "kept_s": kept,
        "segments": len(segs),
        "ratio": kept / original if original else 0,
    }
    console.print(
        f"[green]Wrote[/green] {out}  "
        f"({original/60:.1f}m → {kept/60:.1f}m, {len(segs)} segments)"
    )
    (out.with_suffix(out.suffix + ".json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out
