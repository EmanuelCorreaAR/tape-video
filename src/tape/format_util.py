"""Formato legible para tiempos y resúmenes."""

from __future__ import annotations


def fmt_duration(seconds: float) -> str:
    """12.5 → '12s' | 95 → '1m 35s' | 5540 → '1h 32m'."""
    if seconds < 0:
        seconds = 0.0
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m" if s == 0 else f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def fmt_ts(seconds: float) -> str:
    """Segundos → HH:MM:SS o MM:SS."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def compression_ratio(original_s: float, kept_s: float) -> str:
    if original_s <= 0:
        return "—"
    pct = 100.0 * kept_s / original_s
    return f"{pct:.0f}% del original"
