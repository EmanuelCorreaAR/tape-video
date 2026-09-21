"""Derive activity segments from timeline bins."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rich.console import Console

from tape.db import connect, require_media

console = Console()


def detect_activity(
    db_path: Path,
    *,
    motion_thresh: float = 0.12,
    audio_thresh: float = 0.18,
    min_duration_s: float = 2.0,
    merge_gap_s: float = 1.5,
    pad_s: float = 0.5,
    replace: bool = True,
    quiet: bool = False,
) -> list[tuple[float, float, float]]:
    conn = connect(db_path)
    media = require_media(conn)
    duration = float(media["duration_s"])

    bins = conn.execute(
        "SELECT t0, t1, motion, audio_rms FROM timeline_bins ORDER BY t0"
    ).fetchall()
    if not bins:
        conn.close()
        raise SystemExit("No timeline bins. Run `tape index` first.")

    active_flags: list[tuple[float, float, bool, float]] = []
    for row in bins:
        motion = float(row["motion"] or 0)
        audio = float(row["audio_rms"] or 0)
        active = motion >= motion_thresh or audio >= audio_thresh
        score = max(motion, audio)
        active_flags.append((float(row["t0"]), float(row["t1"]), active, score))

    raw: list[tuple[float, float, float]] = []
    cur_start = None
    cur_end = None
    scores: list[float] = []

    for t0, t1, active, score in active_flags:
        if active:
            if cur_start is None:
                cur_start = t0
                scores = [score]
            else:
                scores.append(score)
            cur_end = t1
        elif cur_start is not None:
            raw.append((cur_start, cur_end or t0, sum(scores) / max(1, len(scores))))
            cur_start = cur_end = None
            scores = []
    if cur_start is not None and cur_end is not None:
        raw.append((cur_start, cur_end, sum(scores) / max(1, len(scores))))

    # Merge close gaps
    merged: list[tuple[float, float, float]] = []
    for start, end, score in raw:
        if not merged:
            merged.append((start, end, score))
            continue
        ps, pe, pscore = merged[-1]
        if start - pe <= merge_gap_s:
            merged[-1] = (ps, end, max(pscore, score))
        else:
            merged.append((start, end, score))

    # Pad + filter short
    final: list[tuple[float, float, float]] = []
    for start, end, score in merged:
        start = max(0.0, start - pad_s)
        end = min(duration, end + pad_s)
        if end - start >= min_duration_s:
            final.append((start, end, score))

    if replace:
        conn.execute("DELETE FROM segments WHERE kind = ? AND source = ?", ("activity", "tape.detect"))

    for start, end, score in final:
        conn.execute(
            """
            INSERT INTO segments(kind, start_s, end_s, score, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("activity", start, end, score, "tape.detect"),
        )
    conn.commit()
    conn.close()

    if not quiet:
        console.print(
            f"[green]Listo[/green] {len(final)} tramos activos "
            f"(movimiento ≥ {motion_thresh:.2f} o audio ≥ {audio_thresh:.2f})"
        )
    return final


def list_segments(db_path: Path, kind: str | None = None) -> list[sqlite3.Row]:
    conn = connect(db_path)
    if kind:
        rows = conn.execute(
            "SELECT * FROM segments WHERE kind = ? ORDER BY start_s", (kind,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM segments ORDER BY start_s").fetchall()
    conn.close()
    return rows
