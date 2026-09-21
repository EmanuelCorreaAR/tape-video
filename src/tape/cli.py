"""tape-video CLI — SQLite para videos largos."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
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
from tape.paths_util import EPILOG, default_clips_dir, default_digest_path, looks_like_video
from tape.render import compress, export_segments, resolve_db

app = typer.Typer(
    name="tape",
    help="tape-video — SQLite para videos largos: indexá, consultá, cortá y comprimí.",
    epilog=EPILOG,
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()


def _handle_ffmpeg(exc: FFmpegNotFoundError) -> None:
    console.print(Panel(str(exc), title="[red]Falta ffmpeg[/red]", border_style="red"))
    console.print("Después:  [bold]tape doctor[/bold]")
    raise typer.Exit(1)


def _ensure_video_arg(path: Path) -> Path:
    path = path.resolve()
    if not path.exists():
        console.print(f"[red]No existe:[/red] {path}")
        raise typer.Exit(1)
    if path.name.endswith(".tape"):
        return path
    if not looks_like_video(path):
        console.print(
            f"[yellow]Aviso:[/yellow] '{path.suffix}' no parece un video típico. "
            "Sigo igual…"
        )
    return path


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


def _ffmpeg_version() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ""
    try:
        out = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
        first = (out.stdout or "").splitlines()[0] if out.stdout else ""
        return first.replace("ffmpeg version ", "").split(" ")[0]
    except OSError:
        return ""


@app.callback()
def main() -> None:
    """tape-video: índice temporal embebido para video largo."""


@app.command()
def version() -> None:
    """Muestra la versión."""
    console.print(f"tape-video {__version__}  (comando: tape)")


@app.command("doctor")
def doctor_cmd() -> None:
    """Chequea que el entorno esté listo (ffmpeg, Python, etc.)."""
    lines = [
        f"[bold]tape-video[/bold] {__version__}",
        "",
    ]
    ok = True

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    ver = _ffmpeg_version()

    if ffmpeg:
        lines.append(f"ffmpeg   [green]ok[/green]  {ver or ''}  ({ffmpeg})")
    else:
        lines.append("ffmpeg   [red]falta[/red]  →  brew install ffmpeg")
        ok = False
    if ffprobe:
        lines.append(f"ffprobe  [green]ok[/green]  ({ffprobe})")
    else:
        lines.append("ffprobe  [red]falta[/red]  →  brew install ffmpeg")
        ok = False

    lines.append("")
    if ok:
        lines.append("[green]Listo.[/green] Probá:")
        lines.append("  tape digest video.mp4")
    else:
        lines.append("[yellow]Instalá ffmpeg y volvé a correr: tape doctor[/yellow]")

    console.print(Panel("\n".join(lines), title="doctor", border_style="green" if ok else "yellow"))
    if not ok:
        raise typer.Exit(1)


@app.command("index")
def index_cmd(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Video de entrada"),
    bin_s: float = typer.Option(1.0, help="Tamaño de cada muestra en segundos"),
    sample_fps: float = typer.Option(1.0, help="Frames por segundo para medir movimiento"),
    force: bool = typer.Option(False, "--force", "-f", help="Reconstruir el índice si ya existe"),
    db: Optional[Path] = typer.Option(None, help="Ruta del .tape de salida"),
) -> None:
    """Analiza el video y crea el índice .tape (movimiento + audio)."""
    video = _ensure_video_arg(video)
    try:
        out = index_video(video, bin_s=bin_s, sample_fps=sample_fps, force=force, db_path=db)
        _print_timeline(out)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("digest")
def digest_cmd(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Video de entrada"),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Video digest (default: VIDEO_digest.mp4 junto al original)",
    ),
    motion: float = typer.Option(0.12, "--motion", "-m", help="Umbral de movimiento 0..1"),
    audio: float = typer.Option(0.18, "--audio", "-a", help="Umbral de audio 0..1"),
    force: bool = typer.Option(False, "--force", "-f", help="Reindexar aunque ya exista .tape"),
) -> None:
    """Todo en uno: indexar (si hace falta) + comprimir a un digest."""
    video = _ensure_video_arg(video)
    out_path = out or default_digest_path(video)
    try:
        db = tape_path_for(video.resolve())
        console.print(
            Panel(
                f"[bold]{video.name}[/bold]\n→ {out_path.name}",
                title="digest",
                border_style="cyan",
            )
        )
        if force or not db.exists():
            console.print("[bold]Paso 1/2[/bold] Indexar")
            index_video(video, force=force or db.exists())
            _print_timeline(db, motion=motion, audio=audio)
            console.print()
        else:
            console.print(f"[dim]Índice existente:[/dim] {db.name}  (usar --force para regenerar)")
            _print_timeline(db, motion=motion, audio=audio)
            console.print()

        console.print("[bold]Paso 2/2[/bold] Comprimir tramos activos")
        compress(video, out_path, motion_thresh=motion, audio_thresh=audio)
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
    table = Table(*rows[0].keys(), show_lines=False)
    for row in rows:
        table.add_row(*[str(row[k]) if row[k] is not None else "" for k in row.keys()])
    console.print(table)
    console.print(f"[dim]{len(rows)} filas[/dim]")
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

    body = [
        f"[bold]Video[/bold]      {media['abs_path']}",
        f"[bold]Índice[/bold]     {db}",
        f"[bold]Duración[/bold]   {fmt_duration(duration)}",
        f"[bold]Tamaño[/bold]     {media['width']}×{media['height']} @ {media['fps']} fps",
        f"[bold]Muestras[/bold]   {n_bins}",
    ]
    if avg_motion is not None:
        body.append(f"[bold]Movimiento[/bold] promedio {avg_motion:.3f}")
    if avg_audio is not None:
        body.append(f"[bold]Audio[/bold]      promedio {avg_audio:.3f}")
    body.append(f"[bold]Tramos[/bold]     {n_segs}")
    if n_segs and kept:
        body.append(
            f"[bold]Digest[/bold]     {fmt_duration(duration)} → {fmt_duration(float(kept))} "
            f"({compression_ratio(duration, float(kept))})"
        )
    console.print(Panel("\n".join(body), title="info", border_style="cyan"))
    _print_timeline(db, motion=motion, audio=audio)


@app.command("detect")
def detect_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    motion: float = typer.Option(0.12, "--motion", "-m", help="Umbral de movimiento 0..1"),
    audio: float = typer.Option(0.18, "--audio", "-a", help="Umbral de audio 0..1"),
    min_duration: float = typer.Option(2.0, help="Descartar tramos más cortos que esto (s)"),
) -> None:
    """Marca tramos activos (movimiento o audio alto)."""
    _, db = _db_only(target)
    console.print(
        f"[bold]Criterio[/bold]: activo si movimiento ≥ {motion:.2f}  O  audio ≥ {audio:.2f}"
    )
    _print_timeline(db, motion=motion, audio=audio)
    segs = detect_activity(
        db,
        motion_thresh=motion,
        audio_thresh=audio,
        min_duration_s=min_duration,
    )
    if not segs:
        console.print("[yellow]No hubo tramos.[/yellow] Bajá -m / -a e intentá de nuevo.")
        return

    table = Table("Nº", "Desde", "Hasta", "Duración", "Intensidad")
    total = 0.0
    for i, (start, end, score) in enumerate(segs, start=1):
        dur = end - start
        total += dur
        table.add_row(str(i), fmt_ts(start), fmt_ts(end), fmt_duration(dur), f"{score:.2f}")
    console.print(table)
    console.print(f"Total activo: [bold]{fmt_duration(total)}[/bold] en {len(segs)} tramos")
    console.print("[dim]Siguiente:  tape digest VIDEO[/dim]")


@app.command("clip")
def clip_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    out_dir: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Carpeta de salida (default: VIDEO_clips/)"
    ),
    kind: str = typer.Option("activity", help="Tipo de segmento"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Solo los N más intensos"),
) -> None:
    """Exporta cada tramo activo como un .mp4 aparte."""
    try:
        video, _db = resolve_db(target)
        dest = out_dir or default_clips_dir(video)
        export_segments(target, dest, kind=kind, limit=limit)
    except FFmpegNotFoundError as e:
        _handle_ffmpeg(e)


@app.command("compress")
def compress_cmd(
    target: Path = typer.Argument(..., help="Video o archivo .tape"),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Video digest (default: VIDEO_digest.mp4)",
    ),
    motion: float = typer.Option(0.12, "--motion", "-m", help="Umbral de movimiento 0..1"),
    audio: float = typer.Option(0.18, "--audio", "-a", help="Umbral de audio 0..1"),
) -> None:
    """Deja solo tramos activos → un video más corto + resumen .txt."""
    try:
        video, db = resolve_db(target)
        out_path = out or default_digest_path(video)
        _print_timeline(db, motion=motion, audio=audio)
        compress(target, out_path, motion_thresh=motion, audio_thresh=audio)
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
        console.print("No hay tramos. Corré:  [bold]tape detect VIDEO[/bold]")
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
                f"Falta el índice: {db}\nCorré primero:  tape index {p.name}\n"
                f"O todo junto:     tape digest {p.name}"
            ) from None
    return p, db


if __name__ == "__main__":
    app()
