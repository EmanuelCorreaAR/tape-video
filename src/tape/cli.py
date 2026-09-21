"""Tape CLI — SQLite para videos largos."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tape import __version__
from tape.db import connect, require_media, tape_path_for
from tape.detect import detect_activity, list_segments
from tape.ffmpeg_util import FFmpegNotFoundError
from tape.format_util import (
    activity_timeline,
    compression_ratio,
    fmt_duration,
    fmt_ts,
    timeline_legend,
)
from tape.index import index_video
from tape.render import compress, export_segments, resolve_db

app = typer.Typer(
    name="tape",
    help="SQLite para videos largos: indexá, consultá, cortá y comprimí.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _handle_ffmpeg(exc: FFmpegNotFoundError) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(1)


def _load_bins(db: Path) -> list[tuple[float, float]]:
    conn = connect(db)
    rows = conn.execute(
        "SELECT motion, audio_rms FROM timeline_bins ORDER BY t0"
    ).fetchall()
    conn.close()
    return [(float(r["motion"] or 0), float(r["audio_rms"] or 0)) for r in rows]


def _print_timeline(
    db: Path,
    *,
    motion: float = 0.12,
    audio: float = 0.18,
) -> None:
    bins = _load_bins(db)
    bar = activity_timeline(bins, motion_thresh=motion, audio_thresh=audio)
    console.print(f"  Timeline: |{bar}|")
    console.print(f"            {timeline_legend()}")


@app.callback()
def main() -> None:
    """Tape: índice temporal embebido para video largo."""


@app.command()
def version() -> None:
    """Muestra la versión."""
    console.print(__version__)


@app.command("doctor")
def doctor_cmd() -> None:
    """Chequea que el entorno esté listo (ffmpeg, Python, etc.)."""
    console.print("[bold]Tape doctor[/bold]")
    console.print(f"  tape:     {__version__}")
    console.print(f"  python:   ok")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg:
        console.print(f"  ffmpeg:   [green]ok[/green]  ({ffmpeg})")
    else:
        console.print("  ffmpeg:   [red]falta[/red]  →  brew install ffmpeg")
    if ffprobe:
        console.print(f"  ffprobe:  [green]ok[/green]  ({ffprobe})")
    else:
        console.print("  ffprobe:  [red]falta[/red]  →  brew install ffmpeg")

    if ffmpeg and ffprobe:
        console.print()
        console.print("[green]Listo para indexar videos.[/green]")
        console.print("  tape digest video.mp4 --out digest.mp4")
    else:
        console.print()
        console.print("[yellow]Instalá ffmpeg y volvé a correr: tape doctor[/yellow]")
        raise typer.Exit(1)


@app.command("index")
def index_cmd(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Video de entrada"),
    bin_s: float = typer.Option(1.0, help="Tamaño de cada muestra en segundos"),
    sample_fps: float = typer.Option(1.0, help="Frames por segundo para medir movimiento"),
    force: bool = typer.Option(False, "--force", help="Reconstruir el índice si ya existe"),
    db: Optional[Path] = typer.Option(None, help="Ruta del .tape de salida"),
) -> None:
    """Analiza el video y crea el índice .tape (movimiento + audio)."""
    try:
        out = index_video(video, bin_s=bin_s, sample_fps=sample_fps, force=force, db_path=db)
        _print_timeline(out)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("digest")
def digest_cmd(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Video de entrada"),
    out: Path = typer.Option(Path("digest.mp4"), "--out", help="Video digest de salida"),
    motion: float = typer.Option(0.12, help="Umbral de movimiento 0..1"),
    audio: float = typer.Option(0.18, help="Umbral de audio 0..1"),
    force: bool = typer.Option(False, "--force", help="Reindexar aunque ya exista .tape"),
) -> None:
    """Todo en uno: indexar (si hace falta) + comprimir a un digest."""
    try:
        db = tape_path_for(video.resolve())
        if force or not db.exists():
            console.print("[bold]Paso 1/2[/bold] Indexar")
            index_video(video, force=force or db.exists())
            _print_timeline(db, motion=motion, audio=audio)
            console.print()
        else:
            console.print(f"[dim]Usando índice existente:[/dim] {db.name}")
            _print_timeline(db, motion=motion, audio=audio)
            console.print()

        console.print("[bold]Paso 2/2[/bold] Comprimir tramos activos")
        compress(video, out, motion_thresh=motion, audio_thresh=audio)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("sql")
def sql_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    query: str = typer.Argument(..., help="Consulta SQL sobre el índice"),
) -> None:
    """Corre SQL contra el .tape."""
    _, db = _db_only(target)
    conn = connect(db)
    try:
        cur = conn.execute(query)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error SQL:[/red] {e}")
        raise typer.Exit(1) from e
    rows = cur.fetchall()
    if not rows:
        console.print("(sin filas)")
        conn.close()
        return
    table = Table(*rows[0].keys())
    for row in rows:
        table.add_row(*[str(row[k]) if row[k] is not None else "" for k in row.keys()])
    console.print(table)
    conn.close()


@app.command("info")
def info_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    motion: float = typer.Option(0.12, help="Umbral para la timeline"),
    audio: float = typer.Option(0.18, help="Umbral para la timeline"),
) -> None:
    """Resumen del índice: duración, muestras, tramos."""
    _, db = _db_only(target)
    conn = connect(db)
    media = require_media(conn)
    n_bins = conn.execute("SELECT COUNT(*) AS c FROM timeline_bins").fetchone()["c"]
    n_segs = conn.execute("SELECT COUNT(*) AS c FROM segments").fetchone()["c"]
    avg_motion = conn.execute("SELECT AVG(motion) AS m FROM timeline_bins").fetchone()["m"]
    avg_audio = conn.execute("SELECT AVG(audio_rms) AS a FROM timeline_bins").fetchone()["a"]
    duration = float(media["duration_s"])
    kept = conn.execute(
        "SELECT COALESCE(SUM(end_s - start_s), 0) AS k FROM segments WHERE kind = 'activity'"
    ).fetchone()["k"]
    conn.close()

    console.print("[bold]Resumen del índice[/bold]")
    console.print(f"  Video:      {media['abs_path']}")
    console.print(f"  Índice:     {db}")
    console.print(f"  Duración:   {fmt_duration(duration)}")
    console.print(f"  Tamaño:     {media['width']}×{media['height']} @ {media['fps']} fps")
    console.print(f"  Muestras:   {n_bins} (1 por segundo aprox.)")
    if avg_motion is not None:
        console.print(f"  Movimiento: promedio {avg_motion:.3f} (0=quieto, 1=máximo del video)")
    if avg_audio is not None:
        console.print(f"  Audio:      promedio {avg_audio:.3f}")
    console.print(f"  Tramos:     {n_segs} detectados")
    _print_timeline(db, motion=motion, audio=audio)
    if n_segs and kept:
        console.print(
            f"  Si comprimís ahora: {fmt_duration(duration)} → {fmt_duration(float(kept))} "
            f"({compression_ratio(duration, float(kept))})"
        )


@app.command("detect")
def detect_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    motion: float = typer.Option(0.12, help="Umbral de movimiento 0..1"),
    audio: float = typer.Option(0.18, help="Umbral de audio 0..1"),
    min_duration: float = typer.Option(2.0, help="Descartar tramos más cortos que esto (s)"),
) -> None:
    """Marca tramos activos (movimiento o audio alto)."""
    _, db = _db_only(target)
    console.print(
        "[bold]Criterio[/bold]: un segundo es activo si "
        f"movimiento ≥ {motion:.2f}  O  audio ≥ {audio:.2f}"
    )
    _print_timeline(db, motion=motion, audio=audio)
    segs = detect_activity(
        db,
        motion_thresh=motion,
        audio_thresh=audio,
        min_duration_s=min_duration,
    )
    if not segs:
        console.print("[yellow]No hubo tramos.[/yellow] Bajá --motion / --audio e intentá de nuevo.")
        return

    table = Table("Nº", "Desde", "Hasta", "Duración", "Intensidad")
    total = 0.0
    for i, (start, end, score) in enumerate(segs, start=1):
        dur = end - start
        total += dur
        table.add_row(
            str(i),
            fmt_ts(start),
            fmt_ts(end),
            fmt_duration(dur),
            f"{score:.2f}",
        )
    console.print(table)
    console.print(
        f"Total activo: [bold]{fmt_duration(total)}[/bold] en {len(segs)} tramos"
    )
    console.print("Siguiente:  tape compress VIDEO --out digest.mp4")
    console.print("O todo junto:  tape digest VIDEO --out digest.mp4")


@app.command("clip")
def clip_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    out_dir: Path = typer.Option(Path("clips"), "--out", help="Carpeta de salida"),
    kind: str = typer.Option("activity", help="Tipo de segmento"),
    limit: Optional[int] = typer.Option(None, help="Solo los N más intensos"),
) -> None:
    """Exporta cada tramo activo como un .mp4 aparte."""
    try:
        export_segments(target, out_dir, kind=kind, limit=limit)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("compress")
def compress_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    out: Path = typer.Option(..., "--out", help="Video digest de salida"),
    motion: float = typer.Option(0.12, help="Umbral de movimiento 0..1"),
    audio: float = typer.Option(0.18, help="Umbral de audio 0..1"),
) -> None:
    """Deja solo tramos activos → un video más corto + resumen .txt."""
    try:
        _, db = _db_only(target)
        _print_timeline(db, motion=motion, audio=audio)
        compress(target, out, motion_thresh=motion, audio_thresh=audio)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("segments")
def segments_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    kind: Optional[str] = typer.Option(None, help="Filtrar por tipo"),
) -> None:
    """Lista los tramos guardados en el índice."""
    _, db = _db_only(target)
    rows = list_segments(db, kind=kind)
    if not rows:
        console.print("No hay tramos. Corré:  tape detect VIDEO")
        return
    table = Table("Nº", "Tipo", "Desde", "Hasta", "Duración", "Intensidad")
    for i, r in enumerate(rows, start=1):
        start = float(r["start_s"])
        end = float(r["end_s"])
        table.add_row(
            str(i),
            r["kind"],
            fmt_ts(start),
            fmt_ts(end),
            fmt_duration(end - start),
            f"{r['score']:.2f}" if r["score"] is not None else "",
        )
    console.print(table)


def _db_only(target: Path) -> tuple[Path, Path]:
    p = target.resolve()
    if p.suffix == ".tape" or str(p).endswith(".mp4.tape") or p.name.endswith(".tape"):
        return Path("."), p
    db = tape_path_for(p)
    if not db.exists():
        try:
            return resolve_db(p)
        except SystemExit:
            raise SystemExit(
                f"Falta el índice: {db}\nCorré primero:  tape index {p.name}"
            ) from None
    return p, db


if __name__ == "__main__":
    app()
