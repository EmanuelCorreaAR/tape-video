import numpy as np

from tape.signals import (
    activity_score,
    audio_peak_flags,
    crop_roi,
    is_active_bin,
    normalize_peak,
    smooth_series,
)


def test_crop_roi_shrinks() -> None:
    arr = np.ones((100, 200), dtype=np.float32)
    roi = crop_roi(arr, margin=0.1)
    assert roi.shape == (80, 160)


def test_smooth_series() -> None:
    vals = [0.0, 1.0, 0.0, 1.0, 0.0]
    sm = smooth_series(vals, window=3)
    assert len(sm) == 5
    assert sm[1] < 1.0  # smoothed spike


def test_normalize_peak() -> None:
    assert normalize_peak([0.0, 2.0, 1.0]) == [0.0, 1.0, 0.5]


def test_audio_peak_flags() -> None:
    rms = [0.1, 0.1, 0.8, 0.2, 0.1]
    flags = audio_peak_flags(rms)
    assert flags[2] == 1


def test_is_active_with_onset() -> None:
    assert is_active_bin(0.05, 0.1, 1, motion_thresh=0.12, audio_thresh=0.18)
    assert not is_active_bin(0.05, 0.05, 0, motion_thresh=0.12, audio_thresh=0.18)


def test_activity_score_boost() -> None:
    assert activity_score(0.2, 0.1, 1) > activity_score(0.2, 0.1, 0)
