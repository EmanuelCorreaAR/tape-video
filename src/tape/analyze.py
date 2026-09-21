"""Estimación de actividad y umbrales adaptativos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tape.db import connect, require_media
from tape.signals import activity_score, is_active_bin


@dataclass
class AnalyzeResult:
    duration_s: float
    n_bins: int
    motion_thresh: float
    audio_thresh: float
    mode: str  # "fixed" | "adaptive"
    active_bins: int
    kept_s: float
    ratio: float
    n_segments_est: int


def _load_scores(
    db_path: Path,
) -> tuple[float, list[tuple[float, float, float, float, int]]]:
    """Returns (duration, [(t0, t1, motion, audio, onset), ...])."""
    conn = connect(db_path)
    media = require_media(conn)
    duration = float(media["duration_s"])
    rows = conn.execute(
        "SELECT t0, t1, motion, audio_rms, audio_onset FROM timeline_bins ORDER BY t0"
    ).fetchall()
    conn.close()
    bins = [
        (
            float(r["t0"]),
            float(r["t1"]),
            float(r["motion"] or 0),
            float(r["audio_rms"] or 0),
            int(r["audio_onset"] or 0),
        )
        for r in rows
    ]
    return duration, bins


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if p <= 0:
        return ordered[0]
    if p >= 100:
        return ordered[-1]
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def estimate_kept(
    bins: list[tuple[float, float, float, float, int]],
    motion_thresh: float,
    audio_thresh: float,
    *,
    merge_gap_s: float = 1.5,
    min_duration_s: float = 2.0,
    pad_s: float = 0.5,
    duration_s: float = 0.0,
) -> tuple[float, int, int]:
    """Returns (kept_s, active_bins, n_segments)."""
    active_flags: list[tuple[float, float, bool]] = []
    active_bins = 0
    for t0, t1, motion, audio, onset in bins:
        active = is_active_bin(
            motion,
            audio,
            onset,
            motion_thresh=motion_thresh,
            audio_thresh=audio_thresh,
        )
        if active:
            active_bins += 1
        active_flags.append((t0, t1, active))

    raw: list[tuple[float, float]] = []
    cur_start = cur_end = None
    for t0, t1, active in active_flags:
        if active:
            if cur_start is None:
                cur_start = t0
            cur_end = t1
        elif cur_start is not None:
            raw.append((cur_start, cur_end or t0))
            cur_start = cur_end = None
    if cur_start is not None and cur_end is not None:
        raw.append((cur_start, cur_end))

    merged: list[tuple[float, float]] = []
    for start, end in raw:
        if not merged:
            merged.append((start, end))
            continue
        ps, pe = merged[-1]
        if start - pe <= merge_gap_s:
            merged[-1] = (ps, end)
        else:
            merged.append((start, end))

    final: list[tuple[float, float]] = []
    for start, end in merged:
        start = max(0.0, start - pad_s)
        end = min(duration_s, end + pad_s) if duration_s else end + pad_s
        if end - start >= min_duration_s:
            final.append((start, end))

    # short videos: allow shorter segments
    if not final and raw:
        for start, end in merged:
            start = max(0.0, start - pad_s)
            end = min(duration_s, end + pad_s) if duration_s else end + pad_s
            if end > start:
                final.append((start, end))

    kept = sum(e - s for s, e in final)
    return kept, active_bins, len(final)


def suggest_adaptive_thresholds(
    bins: list[tuple[float, float, float, float, int]],
    *,
    target_keep: float = 0.45,
) -> tuple[float, float]:
    """
    Elige un umbral sobre score (motion/audio + boost de picos)
    para conservar ~target_keep de los bins más intensos.
    """
    scores = [activity_score(m, a, o) for _, _, m, a, o in bins]
    if not scores:
        return 0.12, 0.18
    p = max(0.0, min(100.0, (1.0 - target_keep) * 100.0))
    t = percentile(scores, p)
    t = max(t, 0.05)
    return t, t


def analyze_db(
    db_path: Path,
    *,
    motion_thresh: float = 0.12,
    audio_thresh: float = 0.18,
    adaptive: bool = True,
    target_keep: float = 0.45,
    active_ratio_trigger: float = 0.85,
) -> AnalyzeResult:
    duration, bins = _load_scores(db_path)
    if not bins:
        raise SystemExit("Sin bins. Corré: tape index VIDEO")

    kept, active_bins, n_segs = estimate_kept(
        bins, motion_thresh, audio_thresh, duration_s=duration
    )
    ratio = kept / duration if duration else 0.0
    mode = "fixed"
    m_t, a_t = motion_thresh, audio_thresh

    if adaptive and ratio >= active_ratio_trigger:
        m_t, a_t = suggest_adaptive_thresholds(bins, target_keep=target_keep)
        kept, active_bins, n_segs = estimate_kept(bins, m_t, a_t, duration_s=duration)
        # short clip: relax min duration inside estimate — already handled
        if duration < 30:
            kept, active_bins, n_segs = estimate_kept(
                bins,
                m_t,
                a_t,
                duration_s=duration,
                min_duration_s=0.5,
                pad_s=0.25,
            )
        ratio = kept / duration if duration else 0.0
        mode = "adaptive"

    return AnalyzeResult(
        duration_s=duration,
        n_bins=len(bins),
        motion_thresh=m_t,
        audio_thresh=a_t,
        mode=mode,
        active_bins=active_bins,
        kept_s=kept,
        ratio=ratio,
        n_segments_est=n_segs,
    )
