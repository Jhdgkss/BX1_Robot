#!/usr/bin/env python3
"""Repeatable, gain-neutral BX1 microphone noise measurement."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import time
import wave
from array import array
from pathlib import Path
from statistics import median

CONDITIONS = (
    "servos_unpowered", "servos_powered_idle", "yaw_servo_powered",
    "yaw_servo_moving", "yaw_powered_idle", "yaw_moving", "speech_test",
)
CONDITION_ALIASES = {
    "yaw_powered_idle": "yaw_servo_powered",
    "yaw_moving": "yaw_servo_moving",
}


def analyse_wav(path: Path, frame_ms: int = 100) -> dict:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frame_count = wav.getnframes()
        raw = wav.readframes(frame_count)
    if width != 2:
        raise ValueError(f"expected 16-bit PCM WAV, got sample width {width}")
    pcm = array("h")
    pcm.frombytes(raw[: len(raw) - len(raw) % 2])
    if sys.byteorder != "little":
        pcm.byteswap()
    mono = [sum(pcm[i:i + channels]) / (32768.0 * channels)
            for i in range(0, len(pcm) - channels + 1, channels)]
    block = max(1, rate * frame_ms // 1000)
    rms_frames, dropout_count = [], 0
    for start in range(0, len(mono), block):
        chunk = mono[start:start + block]
        if not chunk:
            continue
        rms = math.sqrt(sum(value * value for value in chunk) / len(chunk))
        rms_frames.append(20.0 * math.log10(max(rms, 1.0 / 32768.0)))
        if all(abs(value) <= 1.0 / 32768.0 for value in chunk):
            dropout_count += 1
    peak = max((abs(value) for value in mono), default=0.0)
    clipping = sum(1 for value in pcm if abs(value) >= 32767)

    # Standard-library-only Goertzel bank. The reported band value is the RMS
    # level represented by bins from 1–4 kHz, suitable for like-for-like runs.
    window = mono[: min(len(mono), rate * 10)]
    band_power = 0.0
    bin_count = 0
    for hz in range(1000, min(4000, rate // 2 - 1) + 1, 100):
        omega = 2.0 * math.pi * hz / rate
        coeff, q1, q2 = 2.0 * math.cos(omega), 0.0, 0.0
        for value in window:
            q0 = coeff * q1 - q2 + value
            q2, q1 = q1, q0
        band_power += max(0.0, q1 * q1 + q2 * q2 - coeff * q1 * q2)
        bin_count += 1
    band_rms = math.sqrt(band_power / max(1, bin_count)) / max(1, len(window))
    return {
        "sample_rate_hz": rate,
        "channels": channels,
        "duration_s": round(frame_count / max(1, rate), 3),
        "median_rms_dbfs": round(median(rms_frames) if rms_frames else -120.0, 2),
        "peak_dbfs": round(20.0 * math.log10(max(peak, 1.0 / 32768.0)), 2),
        "band_1_4khz_dbfs": round(20.0 * math.log10(max(band_rms, 1.0 / 32768.0)), 2),
        "clipping_count": clipping,
        "dropout_count": dropout_count,
        "dropout_definition": f"{frame_ms} ms frames containing only digital zero",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("condition", choices=CONDITIONS)
    parser.add_argument("--device", default="plughw:0,0")
    parser.add_argument("--rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/diagnostics/audio"))
    parser.add_argument("--analyse-existing", type=Path, help="analyse a WAV without capturing")
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = args.analyse_existing or args.output_dir / f"{stamp}_{args.condition}.wav"
    json_path = args.output_dir / f"{stamp}_{args.condition}.json"
    capture = {"ok": True, "source": "existing_wav"}
    if not args.analyse_existing:
        arecord = shutil.which("arecord")
        if not arecord:
            raise SystemExit("arecord not found; run this diagnostic on the UNO Q Linux processor")
        cmd = [arecord, "-q", "-D", args.device, "-f", "S16_LE", "-r", str(args.rate),
               "-c", str(args.channels), "-d", str(max(1, round(args.duration))), str(wav_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.duration + 10, check=False)
        capture = {"ok": proc.returncode == 0, "returncode": proc.returncode,
                   "stderr": proc.stderr.strip(), "command": cmd}
        if proc.returncode:
            raise SystemExit(json.dumps(capture, indent=2))
    result = {
        "schema": "bx1.audio_noise_diagnostic.v1",
        "condition": args.condition,
        "canonical_condition": CONDITION_ALIASES.get(args.condition, args.condition),
        "selected_alsa_device": args.device,
        "gain_changed": False,
        "capture": capture,
        **analyse_wav(wav_path),
        "wav_output_path": str(wav_path.resolve()),
        "json_result_path": str(json_path.resolve()),
    }
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
