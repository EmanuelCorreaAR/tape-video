from tape.format_util import compression_ratio, fmt_duration, fmt_ts


def test_fmt_duration() -> None:
    assert fmt_duration(12) == "12s"
    assert fmt_duration(95) == "1m 35s"
    assert "1h" in fmt_duration(3725)


def test_fmt_ts() -> None:
    assert fmt_ts(65) == "01:05"
    assert fmt_ts(3725) == "1:02:05"


def test_compression_ratio() -> None:
    assert compression_ratio(100, 25) == "25% del original"
