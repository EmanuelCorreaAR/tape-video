"""Build a .tape index from a video (motion + audio bins)."""

from __future__ import annotations

import hashlib
import math
import tempfile
import wave
from array import array
from pathlib import Path

import numpy as np
from PIL import Image
from rich.console import Console
from rich.progress import Progress

from tape.db import connect, init_db, tape_path_for
from tape.ffmpeg_util import ffmpeg_bin, run
from tape.format_util import fmt_duration
from tape.probe import probe
from tape.signals import audio_peak_flags, crop_roi, normalize_peak, smooth_series

console = Console()

ROI_MARGIN = 0.12
SMOOTH_WINDOW = 3


def _sha256_prefix(path: Path, limit: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        remaining = limit
        while remaining > 0:
            chunk = f.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def _extract_audio_wav(video: Path, wav_path: Path, sample_rate: int = 16000) -> bool:
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        str(wav_path),
    ]
    result = run(cmd, check=False)
    return result.returncode == 0 and wav_path.exists()


def _audio_rms_bins(wav_path: Path, duration_s: float, bin_s: float) -> list[float]:
    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        nch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth == 2:
        samples = array("h")
        samples.frombytes(raw)
        data = np.asarray(samples, dtype=np.float32)
    else:
        # fallback: treat as unsigned 8-bit
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0

    if nch > 1:
        data = data.reshape(-1, nch).mean(axis=1)

    n_bins = max(1, int(math.ceil(duration_s / bin_s)))
    samples_per_bin = max(1, int(rate * bin_s))
    rms = []
    for i in range(n_bins):
        start = i * samples_per_bin
        end = min(len(data), start + samples_per_bin)
        if start >= len(data) or end <= start:
            rms.append(0.0)
            continue
        chunk = data[start:end]
        val = float(np.sqrt(np.mean(np.square(chunk))))
        rms.append(val)

    peak = max(rms) if rms else 1.0
    if peak <= 0:
        return [0.0] * len(rms)
    return [min(1.0, v / peak) for v in rms]


def _sample_frames(video: Path, out_dir: Path, fps: float = 1.0, width: int = 320) -> list[Path]:
    pattern = str(out_dir / "frame_%06d.jpg")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps={fps},scale={width}:-2",
        "-q:v",
        "5",
        pattern,
    ]
    run(cmd)
    return sorted(out_dir.glob("frame_*.jpg"))


def _motion_luma_from_frames(
    frames: list[Path],
    *,
    roi_margin: float = ROI_MARGIN,
) -> tuple[list[float], list[float]]:
    if not frames:
        return [], []

    prev = None
    lumas: list[float] = []
    diffs: list[float] = []

    for path in frames:
        img = Image.open(path).convert("L")
        arr = np.asarray(img, dtype=np.float32) / 255.0
        roi = crop_roi(arr, margin=roi_margin)
        lumas.append(float(roi.mean()))
        if prev is None:
            diffs.append(0.0)
        else:
            diffs.append(float(np.mean(np.abs(roi - prev))))
        prev = roi

    return normalize_peak(diffs), lumas


def _onsets(rms: list[float]) -> list[int]:
    return audio_peak_flags(rms)


def index_video(
    video: Path,
    *,
    bin_s: float = 1.0,
    sample_fps: float = 1.0,
    force: bool = False,
    db_path: Path | None = None,
) -> Path:
    video = video.resolve()
    if not video.exists():
        raise SystemExit(f"Video not found: {video}")

    out = db_path or tape_path_for(video)
    if out.exists() and not force:
        raise SystemExit(f"Index already exists: {out} (pass --force to rebuild)")

    info = probe(video)
    duration = info["duration_s"]
    if duration <= 0:
        raise SystemExit("Could not read video duration via ffprobe.")

    console.print(
        f"[bold]Indexando[/bold] {video.name}  "
        f"({fmt_duration(duration)})"
    )

    with tempfile.TemporaryDirectory(prefix="tape-") as tmp:
        tmp_path = Path(tmp)
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        wav_path = tmp_path / "audio.wav"

        with Progress(console=console) as progress:
            task = progress.add_task("Muestreando frames…", total=3)
            frames = _sample_frames(video, frames_dir, fps=sample_fps)
            progress.advance(task)

            progress.update(task, description="Midiendo movimiento…")
            motions, lumas = _motion_luma_from_frames(frames)
            progress.advance(task)

            progress.update(task, description="Analizando audio…")
            audio_ok = False
            rms: list[float] = []
            if info["has_audio"]:
                audio_ok = _extract_audio_wav(video, wav_path)
                if audio_ok:
                    rms = _audio_rms_bins(wav_path, duration, bin_s)
            progress.advance(task)

    n_bins = max(1, int(math.ceil(duration / bin_s)))
    # Align frame-based series to bins (1 fps sampling ≈ 1s bins by default)
    while len(motions) < n_bins:
        motions.append(0.0)
        lumas.append(0.0)
    motions = motions[:n_bins]
    lumas = lumas[:n_bins]

    if not rms:
        rms = [0.0] * n_bins
    while len(rms) < n_bins:
        rms.append(0.0)
    rms = rms[:n_bins]

    # Suavizado temporal + picos de audio
    motions = smooth_series(motions, window=SMOOTH_WINDOW)
    rms = smooth_series(rms, window=SMOOTH_WINDOW)
    motions = normalize_peak(motions)
    rms = normalize_peak(rms)
    onsets = _onsets(rms)

    if out.exists():
        out.unlink()

    conn = connect(out)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO media(id, path, abs_path, sha256, duration_s, fps, width, height, has_audio)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video.name,
            str(video),
            _sha256_prefix(video),
            duration,
            info["fps"],
            info["width"],
            info["height"],
            info["has_audio"],
        ),
    )
    for key, value in (
        ("bin_s", str(bin_s)),
        ("sample_fps", str(sample_fps)),
        ("roi_margin", str(ROI_MARGIN)),
        ("smooth_window", str(SMOOTH_WINDOW)),
        ("signal_version", "1"),
    ):
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?)",
            (key, value),
        )

    rows = []
    for i in range(n_bins):
        t0 = i * bin_s
        t1 = min(duration, (i + 1) * bin_s)
        rows.append((t0, t1, motions[i], rms[i], onsets[i], lumas[i]))
    conn.executemany(
        """
        INSERT INTO timeline_bins(t0, t1, motion, audio_rms, audio_onset, luma)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    active_hint = sum(1 for m, a in zip(motions, rms) if m >= 0.12 or a >= 0.18)
    console.print()
    console.print("[bold green]Índice listo[/bold green]")
    console.print(f"  Archivo:     {out.name}")
    console.print(f"  Qué es:      base SQLite con la línea de tiempo del video")
    console.print(f"  Duración:    {fmt_duration(duration)}")
    console.print(f"  Resolución:  cada {bin_s:g}s → {n_bins} muestras")
    console.print(
        f"  Señal:       ROI central ({int((1-2*ROI_MARGIN)*100)}%) + smooth + picos audio"
        if info["has_audio"] and rms and max(rms) > 0
        else f"  Señal:       ROI central + smooth (sin audio usable)"
    )
    console.print(
        f"  Vista previa: ~{active_hint}s pasarían el umbral default de actividad "
        f"({100 * active_hint / max(1, n_bins):.0f}% del video)"
    )
    console.print()
    console.print("Siguiente:")
    console.print(f"  tape detect {video.name}")
    console.print(f"  tape compress {video.name} --out digest.mp4")
    return out
