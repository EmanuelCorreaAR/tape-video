"""Mejora de señales: ROI, smoothing y picos de audio."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def crop_roi(arr: np.ndarray, margin: float = 0.12) -> np.ndarray:
    """Ignora bordes (shake, UI, letterbox). margin=0.12 → usa el 76% central."""
    if arr.ndim != 2:
        raise ValueError("crop_roi espera imagen 2D")
    margin = max(0.0, min(0.4, margin))
    h, w = arr.shape
    y0 = int(h * margin)
    y1 = max(y0 + 1, int(h * (1.0 - margin)))
    x0 = int(w * margin)
    x1 = max(x0 + 1, int(w * (1.0 - margin)))
    return arr[y0:y1, x0:x1]


def smooth_series(values: Sequence[float], window: int = 3) -> list[float]:
    """Media móvil centrada; reduce spikes de un solo frame."""
    if window < 2 or len(values) < 2:
        return [float(v) for v in values]
    w = window if window % 2 == 1 else window + 1
    half = w // 2
    arr = np.asarray(values, dtype=np.float64)
    # pad edges
    padded = np.pad(arr, (half, half), mode="edge")
    kernel = np.ones(w, dtype=np.float64) / w
    out = np.convolve(padded, kernel, mode="valid")
    return [float(x) for x in out]


def normalize_peak(values: Sequence[float]) -> list[float]:
    vals = [float(v) for v in values]
    peak = max(vals) if vals else 1.0
    if peak <= 0:
        return [0.0] * len(vals)
    return [min(1.0, v / peak) for v in vals]


def audio_peak_flags(
    rms: Sequence[float],
    *,
    factor: float = 1.6,
    min_delta: float = 0.06,
    local_window: int = 5,
) -> list[int]:
    """
    Marca picos / onsets de audio (golpes, voz, clics).
    Combina salto vs bin anterior + ser máximo local.
    """
    n = len(rms)
    out = [0] * n
    if n < 2:
        return out

    half = max(1, local_window // 2)
    for i in range(1, n):
        prev = float(rms[i - 1])
        cur = float(rms[i])
        jump = cur > prev * factor and (cur - prev) >= min_delta

        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        neighborhood = [float(rms[j]) for j in range(lo, hi)]
        local_max = cur >= max(neighborhood) - 1e-9
        # pico relativo a la media local
        local_mean = sum(neighborhood) / len(neighborhood)
        above_local = cur >= local_mean + min_delta

        if jump or (local_max and above_local and cur >= 0.15):
            out[i] = 1
    return out


def activity_score(
    motion: float,
    audio: float,
    onset: int = 0,
    *,
    onset_boost: float = 0.35,
) -> float:
    """Score 0..1; los picos de audio empujan la actividad."""
    base = max(float(motion), float(audio))
    if onset:
        base = min(1.0, base + onset_boost)
    return base


def is_active_bin(
    motion: float,
    audio: float,
    onset: int,
    *,
    motion_thresh: float,
    audio_thresh: float,
) -> bool:
    """
    Activo si:
    - movimiento alto en ROI, o
    - audio alto, o
    - pico de audio con algo de nivel (evita silencio con click de ruido)
    """
    if motion >= motion_thresh:
        return True
    if audio >= audio_thresh:
        return True
    if onset and audio >= max(0.08, audio_thresh * 0.45):
        return True
    return False
