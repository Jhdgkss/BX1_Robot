from __future__ import annotations

try:
    import dots_tts  # noqa: F401
    import torch
except Exception as exc:
    raise SystemExit(f"Dot.TTS import failed: {exc}")

print("dots_tts: OK")
print("torch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "not available")
