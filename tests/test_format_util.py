from pathlib import Path

from tape.analyze import percentile, suggest_adaptive_thresholds
from tape.format_util import activity_timeline, compression_ratio, fmt_duration, fmt_ts
from tape.paths_util import default_clips_dir, default_digest_path, looks_like_video


def test_fmt_duration() -> None:
    assert fmt_duration(12) == "12s"
    assert fmt_duration(95) == "1m 35s"
    assert "1h" in fmt_duration(3725)


def test_fmt_ts() -> None:
    assert fmt_ts(65) == "01:05"
    assert fmt_ts(3725) == "1:02:05"


def test_activity_timeline() -> None:
    bins = [(0.0, 0.0), (0.5, 0.0), (0.0, 0.0), (0.0, 0.5)]
    bar = activity_timeline(bins, width=4)
    assert len(bar) == 4
    assert "█" in bar
    assert "·" in bar


def test_compression_ratio() -> None:
    assert compression_ratio(100, 25) == "25% del original"


def test_default_digest_path() -> None:
    p = default_digest_path(Path("/tmp/partido.mp4"))
    assert p.name == "partido_digest.mp4"


def test_default_clips_dir() -> None:
    p = default_clips_dir(Path("/tmp/partido.mp4"))
    assert p.name == "partido_clips"


def test_looks_like_video() -> None:
    assert looks_like_video(Path("a.mp4"))
    assert looks_like_video(Path("a.MOV"))
    assert not looks_like_video(Path("a.mp4.tape"))


def test_percentile() -> None:
    vals = [0.0, 0.25, 0.5, 0.75, 1.0]
    assert percentile(vals, 0) == 0.0
    assert percentile(vals, 100) == 1.0
    assert 0.4 <= percentile(vals, 50) <= 0.6


def test_suggest_adaptive() -> None:
    bins = [(float(i), float(i + 1), i / 10, 0.0, 0) for i in range(10)]
    m, a = suggest_adaptive_thresholds(bins, target_keep=0.3)
    assert m == a
    assert m > 0
