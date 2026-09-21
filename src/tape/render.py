"""Cut clips and build condensed digests with ffmpeg."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from tape.db import connect, require_media, tape_path_for
from tape.detect import detect_activity, list_segments
from tape.ffmpeg_util import ffmpeg_bin, run
from tape.format_util import compression_ratio, fmt_duration, fmt_ts

console = Console()


def resolve_db(video_or_db: Path) -> tuple[Path, Path]:
    """Return (video_path, db_path)."""
    p = video_or_db.resolve()
    if p.suffix == ".tape" or str(p).endswith(".tape"):
        conn = connect(p)
        media = require_media(conn)
        video = Path(media["abs_path"])
        conn.close()
        if not video.exists():
            raise SystemExit(
                f"El índice apunta a un video que no existe:\n  {video}\n"
                "Reindexá con:  tape index RUTA_AL_VIDEO --force"
            )
        return video, p
    db = tape_path_for(p)
    if not db.exists():
        raise SystemExit(
            f"Falta el índice: {db}\nCorré primero:  tape index {p.name}"
        )
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
    console.print(f"[bold]Exportando[/bold] {len(segs)} clips → {out_dir}/")
    for i, seg in enumerate(segs, start=1):
        start = float(seg["start_s"])
        end = float(seg["end_s"])
        out = out_dir / f"{kind}_{i:03d}_{start:.1f}-{end:.1f}.mp4"
        clip_range(video, start, end, out)
        paths.append(out)
        console.print(
            f"  [{i}/{len(segs)}] {fmt_ts(start)} → {fmt_ts(end)}  "
            f"({fmt_duration(end - start)})  →  {out.name}"
        )
    console.print(f"[green]Listo[/green] {len(paths)} archivos en {out_dir.resolve()}")
    return paths


def compress(
    video_or_db: Path,
    out: Path,
    *,
    kind: str = "activity",
    motion_thresh: float = 0.12,
    audio_thresh: float = 0.18,
    adaptive: bool = True,
    target_keep: float = 0.45,
) -> Path:
    from tape.analyze import analyze_db

    video, db = resolve_db(video_or_db)
    analysis = analyze_db(
        db,
        motion_thresh=motion_thresh,
        audio_thresh=audio_thresh,
        adaptive=adaptive,
        target_keep=target_keep,
    )
    m_t = analysis.motion_thresh
    a_t = analysis.audio_thresh

    if analysis.mode == "adaptive":
        console.print(
            f"[yellow]Umbrales fijos dejaban casi todo activo.[/yellow] "
            f"Paso a modo adaptativo → conservar ~{target_keep:.0%} más intenso "
            f"(motion/audio ≥ {m_t:.2f})"
        )
    else:
        console.print(
            f"[bold]Buscando tramos activos[/bold] "
            f"(movimiento ≥ {m_t:.2f} o audio ≥ {a_t:.2f})…"
        )

    min_dur = 2.0 if analysis.duration_s >= 30 else 0.5
    pad = 0.5 if analysis.duration_s >= 30 else 0.25

    detect_activity(
        db,
        motion_thresh=m_t,
        audio_thresh=a_t,
        min_duration_s=min_dur,
        pad_s=pad,
        quiet=True,
    )
    segs = list_segments(db, kind=kind)
    if not segs:
        raise SystemExit(
            "No encontré tramos activos. Probá bajar umbrales:\n"
            "  tape digest VIDEO -m 0.05 -a 0.05 --no-adaptive"
        )

    kept_est = sum(float(s["end_s"]) - float(s["start_s"]) for s in segs)
    ratio_est = kept_est / analysis.duration_s if analysis.duration_s else 0
    if ratio_est >= 0.95:
        console.print(
            Panel(
                "Este video casi no tiene pausas detectables.\n"
                "El digest va a quedar casi igual al original.\n\n"
                "Probá un video más largo, o:\n"
                "  tape analyze VIDEO\n"
                "  tape digest VIDEO --target-keep 0.30",
                title="[yellow]Poco que recortar[/yellow]",
                border_style="yellow",
            )
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f".tape_compress_{out.stem}"
    work.mkdir(exist_ok=True)
    parts: list[Path] = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Cortando tramos…", total=len(segs))
        for i, seg in enumerate(segs, start=1):
            part = work / f"part_{i:04d}.mp4"
            clip_range(video, float(seg["start_s"]), float(seg["end_s"]), part)
            parts.append(part)
            progress.advance(task)

    console.print("Uniendo clips…")
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

    report_path = out.with_suffix(out.suffix + ".txt")
    lines = [
        "tape-video — resumen del digest",
        "=" * 40,
        f"Original:   {fmt_duration(original)}",
        f"Digest:     {fmt_duration(kept)}  ({compression_ratio(original, kept)})",
        f"Tramos:     {len(segs)}",
        f"Modo:       {analysis.mode}",
        f"Video:      {out.resolve()}",
        "",
        "Qué se consideró activo:",
        f"  movimiento ≥ {m_t:.2f}  O  audio ≥ {a_t:.2f}",
        "",
        "Tramos incluidos (tiempo en el original):",
    ]
    for i, seg in enumerate(segs, start=1):
        start = float(seg["start_s"])
        end = float(seg["end_s"])
        score = float(seg["score"] or 0)
        lines.append(
            f"  {i:2d}. {fmt_ts(start)} → {fmt_ts(end)}  "
            f"({fmt_duration(end - start)})  intensidad={score:.2f}"
        )
    lines.append("")
    lines.append("Abrí el .mp4 para ver el resultado.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    meta = {
        "original_s": original,
        "kept_s": kept,
        "segments": len(segs),
        "ratio": kept / original if original else 0,
        "mode": analysis.mode,
        "motion_thresh": m_t,
        "audio_thresh": a_t,
        "video": str(out.resolve()),
        "report": str(report_path.resolve()),
        "tramos": [
            {
                "inicio": fmt_ts(float(s["start_s"])),
                "fin": fmt_ts(float(s["end_s"])),
                "duracion_s": float(s["end_s"]) - float(s["start_s"]),
                "intensidad": float(s["score"] or 0),
            }
            for s in segs
        ],
    }
    json_path = out.with_suffix(out.suffix + ".json")
    json_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    console.print()
    note = ""
    if kept / original >= 0.95 if original else False:
        note = "\n\n[yellow]Casi no se recortó: el video no tiene pausas claras.[/yellow]"
    summary = (
        f"[bold]{fmt_duration(original)}[/bold]  →  [bold green]{fmt_duration(kept)}[/bold green]"
        f"  ({compression_ratio(original, kept)})\n"
        f"Tramos: {len(segs)}  ·  modo: {analysis.mode}\n\n"
        f"[cyan]Video[/cyan]    {out.resolve()}\n"
        f"[cyan]Resumen[/cyan]  {report_path.resolve()}\n"
        f"[cyan]JSON[/cyan]     {json_path.resolve()}\n\n"
        f"[dim]Activo = movimiento ≥ {m_t:.2f} o audio ≥ {a_t:.2f}[/dim]"
        f"{note}"
    )
    console.print(Panel(summary, title="[bold green]Digest listo[/bold green]", border_style="green"))
    return out
