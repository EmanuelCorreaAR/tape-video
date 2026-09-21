"""Tape CLI — SQLite for long videos."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tape import __version__
from tape.db import connect, require_media, tape_path_for
from tape.detect import detect_activity, list_segments
from tape.ffmpeg_util import FFmpegNotFoundError
from tape.index import index_video
from tape.render import compress, export_segments, resolve_db

app = typer.Typer(
    name="tape",
    help="SQLite for long videos — index, query, clip, compress.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _handle_ffmpeg(exc: FFmpegNotFoundError) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(1)


@app.callback()
def main() -> None:
    """Tape: embedded temporal database for long video."""


@app.command()
def version() -> None:
    """Print version."""
    console.print(__version__)


@app.command("index")
def index_cmd(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Input video"),
    bin_s: float = typer.Option(1.0, help="Timeline bin size in seconds"),
    sample_fps: float = typer.Option(1.0, help="Frame sample rate for motion"),
    force: bool = typer.Option(False, "--force", help="Rebuild index if it exists"),
    db: Optional[Path] = typer.Option(None, help="Output .tape path"),
) -> None:
    """Build a .tape index (motion + audio bins)."""
    try:
        index_video(video, bin_s=bin_s, sample_fps=sample_fps, force=force, db_path=db)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("sql")
def sql_cmd(
    target: Path = typer.Argument(..., help="Video or .tape file"),
    query: str = typer.Argument(..., help="SQL SELECT against the tape DB"),
) -> None:
    """Run SQL against a .tape database."""
    _, db = _db_only(target)
    conn = connect(db)
    try:
        cur = conn.execute(query)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]SQL error:[/red] {e}")
        raise typer.Exit(1) from e
    rows = cur.fetchall()
    if not rows:
        console.print("(no rows)")
        conn.close()
        return
    table = Table(*rows[0].keys())
    for row in rows:
        table.add_row(*[str(row[k]) if row[k] is not None else "" for k in row.keys()])
    console.print(table)
    conn.close()


@app.command("info")
def info_cmd(target: Path = typer.Argument(..., help="Video or .tape file")) -> None:
    """Show media + bin summary."""
    _, db = _db_only(target)
    conn = connect(db)
    media = require_media(conn)
    n_bins = conn.execute("SELECT COUNT(*) AS c FROM timeline_bins").fetchone()["c"]
    n_segs = conn.execute("SELECT COUNT(*) AS c FROM segments").fetchone()["c"]
    avg_motion = conn.execute("SELECT AVG(motion) AS m FROM timeline_bins").fetchone()["m"]
    console.print(f"db:       {db}")
    console.print(f"video:    {media['abs_path']}")
    console.print(f"duration: {media['duration_s']:.1f}s")
    console.print(f"size:     {media['width']}x{media['height']} @ {media['fps']}")
    console.print(f"bins:     {n_bins} (avg motion={avg_motion:.3f})" if avg_motion else f"bins: {n_bins}")
    console.print(f"segments: {n_segs}")
    conn.close()


@app.command("detect")
def detect_cmd(
    target: Path = typer.Argument(..., help="Video or .tape file"),
    motion: float = typer.Option(0.12, help="Motion threshold 0..1"),
    audio: float = typer.Option(0.18, help="Audio RMS threshold 0..1"),
    min_duration: float = typer.Option(2.0, help="Drop segments shorter than this"),
) -> None:
    """Detect activity segments from timeline bins."""
    _, db = _db_only(target)
    segs = detect_activity(
        db,
        motion_thresh=motion,
        audio_thresh=audio,
        min_duration_s=min_duration,
    )
    for i, (start, end, score) in enumerate(segs, start=1):
        console.print(f"{i:3d}  {start:8.1f} → {end:8.1f}  score={score:.3f}")


@app.command("clip")
def clip_cmd(
    target: Path = typer.Argument(..., help="Video or .tape file"),
    out_dir: Path = typer.Option(Path("clips"), "--out", help="Output directory"),
    kind: str = typer.Option("activity", help="Segment kind"),
    limit: Optional[int] = typer.Option(None, help="Keep top-N by score"),
) -> None:
    """Export segment clips with ffmpeg."""
    try:
        export_segments(target, out_dir, kind=kind, limit=limit)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("compress")
def compress_cmd(
    target: Path = typer.Argument(..., help="Video or .tape file"),
    out: Path = typer.Option(..., "--out", help="Output digest video"),
    motion: float = typer.Option(0.12, help="Motion threshold 0..1"),
    audio: float = typer.Option(0.18, help="Audio RMS threshold 0..1"),
) -> None:
    """Keep only activity segments → condensed video."""
    try:
        compress(target, out, motion_thresh=motion, audio_thresh=audio)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("segments")
def segments_cmd(
    target: Path = typer.Argument(..., help="Video or .tape file"),
    kind: Optional[str] = typer.Option(None, help="Filter by kind"),
) -> None:
    """List stored segments."""
    _, db = _db_only(target)
    rows = list_segments(db, kind=kind)
    if not rows:
        console.print("(no segments)")
        return
    table = Table("id", "kind", "start", "end", "score", "source")
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["kind"],
            f"{r['start_s']:.2f}",
            f"{r['end_s']:.2f}",
            f"{r['score']:.3f}" if r["score"] is not None else "",
            r["source"],
        )
    console.print(table)


def _db_only(target: Path) -> tuple[Path, Path]:
    p = target.resolve()
    if p.suffix == ".tape" or str(p).endswith(".mp4.tape") or p.name.endswith(".tape"):
        return Path("."), p
    db = tape_path_for(p)
    if not db.exists():
        # also allow passing foo.mp4.tape explicitly already handled
        try:
            return resolve_db(p)
        except SystemExit:
            raise SystemExit(f"Missing index: {db}. Run `tape index {p}` first.") from None
    return p, db


if __name__ == "__main__":
    app()
