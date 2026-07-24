"""Prepare a clean Dot.TTS reference WAV for Robot Brain.

Usage:
    python tools/prepare_reference_voice.py "C:\\path\\to\\sample.wav"

Output:
    runtime/<profile>/dottts/reference_audio/<name>_clean_24k_mono.wav

The tool trims silence, downmixes to mono, normalises level, resamples to
24 kHz and writes 16-bit PCM WAV. It uses only numpy + Python's wave module.
"""
from __future__ import annotations

import argparse
import re
import wave
from pathlib import Path
from typing import Any, Dict

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parent.parent


def safe_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^a-zA-Z0-9_.\-]+", "_", stem).strip("_.-")
    return stem or "reference_voice"


def prepare_reference_wav(source: Path, target: Path, target_sr: int = 24000, max_seconds: float = 10.0) -> Dict[str, Any]:
    with wave.open(str(source), "rb") as wf:
        channels = int(wf.getnchannels())
        sample_width = int(wf.getsampwidth())
        sr = int(wf.getframerate())
        frames = int(wf.getnframes())
        raw = wf.readframes(frames)

    if sample_width == 1:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {sample_width} byte(s). Use 16-bit PCM WAV.")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    if audio.size < sr:
        raise RuntimeError("Reference WAV is too short. Use a clean speech sample of at least 3 seconds.")

    audio = audio - float(audio.mean())

    frame = max(1, int(0.025 * sr))
    hop = max(1, int(0.010 * sr))
    if audio.size > frame:
        starts = np.arange(0, audio.size - frame + 1, hop)
        rms = np.sqrt(np.array([np.mean(audio[s:s + frame] ** 2) for s in starts]) + 1e-12)
        db = 20.0 * np.log10(rms + 1e-12)
        threshold = max(-45.0, float(np.percentile(db, 80)) - 35.0)
        active = np.where(db > threshold)[0]
        if active.size:
            start = max(0, int(starts[int(active[0])] - 0.15 * sr))
            end = min(audio.size, int(starts[int(active[-1])] + frame + 0.25 * sr))
            audio = audio[start:end]

    max_len = int(max_seconds * sr)
    if audio.size > max_len:
        sq = audio.astype(np.float64) ** 2
        csum = np.concatenate([np.zeros(1), np.cumsum(sq)])
        energy = csum[max_len:] - csum[:-max_len]
        best = int(np.argmax(energy))
        audio = audio[best:best + max_len]

    if sr != target_sr:
        old_x = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
        new_len = max(1, int(round(audio.size * target_sr / sr)))
        new_x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        audio = np.interp(new_x, old_x, audio).astype(np.float32)
        sr = target_sr

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak <= 1e-6:
        raise RuntimeError("Reference WAV appears silent after trimming.")
    target_peak = 10 ** (-3.0 / 20.0)
    audio = np.clip(audio / peak * target_peak, -0.999, 0.999)
    pcm = (audio * 32767.0).astype("<i2")

    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if audio.size else 0.0
    return {
        "prepared_path": str(target),
        "sample_rate": int(sr),
        "duration_sec": round(float(audio.size / sr), 3),
        "peak_dbfs": round(float(20 * np.log10(float(np.max(np.abs(audio))) + 1e-12)), 2),
        "rms_dbfs": round(float(20 * np.log10(rms + 1e-12)), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a Robot Brain/Dot.TTS reference WAV.")
    parser.add_argument("source", help="Input WAV file")
    parser.add_argument("--max-seconds", type=float, default=10.0, help="Maximum output duration, default 10 seconds")
    parser.add_argument("--target-sr", type=int, default=24000, help="Output sample rate, default 24000")
    parser.add_argument("--profile", default="bx1", help="Robot profile ID, default bx1")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Input file not found: {source}")
    profile = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(args.profile)).strip("_").lower() or "bx1"
    voices_dir = PROJECT_DIR / "runtime" / profile / "dottts" / "reference_audio"
    target = voices_dir / f"{safe_stem(source.name)}_clean_24k_mono.wav"
    meta = prepare_reference_wav(source, target, target_sr=args.target_sr, max_seconds=args.max_seconds)
    print("Prepared reference voice:")
    for key, value in meta.items():
        print(f"  {key}: {value}")
    print("\nUse this path in the Robot Brain voice profile:")
    print(f"  runtime/{profile}/dottts/reference_audio/{target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
