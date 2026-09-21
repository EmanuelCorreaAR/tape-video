"""Helpers de UX del CLI."""

from __future__ import annotations

from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"}


def default_digest_path(video: Path) -> Path:
    """partido.mp4 → partido_digest.mp4 (junto al video)."""
    video = video.resolve()
    return video.with_name(f"{video.stem}_digest.mp4")


def default_clips_dir(video: Path) -> Path:
    video = video.resolve()
    return video.with_name(f"{video.stem}_clips")


def looks_like_video(path: Path) -> bool:
    if path.name.endswith(".tape"):
        return False
    return path.suffix.lower() in VIDEO_SUFFIXES


EPILOG = """
Ejemplos:
  tape doctor
  tape analyze partido.mp4
  tape digest partido.mp4
  tape digest partido.mp4 --target-keep 0.30
  tape info partido.mp4
  tape sql partido.mp4 "SELECT t0, motion FROM timeline_bins LIMIT 5"

Más info: https://github.com/EmanuelCorreaAR/tape-video
"""
