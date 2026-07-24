from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from faster_whisper import WhisperModel


def main() -> int:
    attempts = [("cuda", "int8_float16"), ("cpu", "int8")]
    errors = []
    for device, compute in attempts:
        try:
            print(f"Loading large-v3-turbo on {device}/{compute}...")
            WhisperModel("large-v3-turbo", device=device, compute_type=compute)
            print(f"SUCCESS: faster-whisper is ready on {device}/{compute}.")
            return 0
        except Exception as exc:
            errors.append(f"{device}/{compute}: {exc}")
            print(f"Attempt failed: {exc}")
    print("No backend could be prepared:")
    for error in errors:
        print(" -", error)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
