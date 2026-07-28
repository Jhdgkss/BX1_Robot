#!/usr/bin/env python3
import math
import tempfile
import wave
from pathlib import Path

from audio_noise_diagnostic import analyse_wav

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "tone.wav"
    rate = 16000
    samples = [int(32767 * 0.1 * math.sin(2 * math.pi * 2000 * i / rate)) for i in range(rate)]
    raw = bytearray()
    for value in samples:
        raw.extend(int(value).to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(raw)
    result = analyse_wav(path)
    assert result["sample_rate_hz"] == 16000
    assert result["channels"] == 1
    assert -24.0 < result["median_rms_dbfs"] < -22.0
    assert result["band_1_4khz_dbfs"] > -60.0
    assert result["clipping_count"] == 0
    assert result["dropout_count"] == 0
print("PASS: phase-one audio diagnostic analysis")
