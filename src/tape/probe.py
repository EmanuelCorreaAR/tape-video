"""ffprobe wrappers."""

from __future__ import annotations

import json
from pathlib import Path

from tape.ffmpeg_util import ffprobe_bin, run


def probe(video: Path) -> dict:
    cmd = [
        ffprobe_bin(),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video),
    ]
    result = run(cmd)
    data = json.loads(result.stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
        None,
    )
    duration = float(data.get("format", {}).get("duration") or 0)
    fps = None
    width = height = None
    if video_stream:
        width = int(video_stream.get("width") or 0) or None
        height = int(video_stream.get("height") or 0) or None
        rate = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
        if rate and rate != "0/0":
            num, den = rate.split("/")
            den_f = float(den)
            if den_f:
                fps = float(num) / den_f
    return {
        "duration_s": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "has_audio": 1 if audio_stream else 0,
    }
