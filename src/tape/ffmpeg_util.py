"""Locate ffmpeg / ffprobe on PATH."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache


class FFmpegNotFoundError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegNotFoundError(
            "ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`) and retry."
        )
    return path


@lru_cache(maxsize=1)
def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FFmpegNotFoundError(
            "ffprobe not found on PATH. Install ffmpeg (e.g. `brew install ffmpeg`) and retry."
        )
    return path


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
    )
