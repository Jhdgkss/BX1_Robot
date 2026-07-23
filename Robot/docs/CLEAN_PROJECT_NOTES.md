# BX1 Clean Project Notes - 2026-07-05

## Cleaned Robot Brain build

Base snapshot: `Robot_Brain_V1_snapshot_20260705_213659`.

Applied:

- `Robot_Brain_V1_3_0_STABILITY_PATCH`
- `Robot_Brain_V1_3_1_DOUBLE_SPEAK_HOTFIX`

Then cleaned root launch scripts down to three visible files:

- `START_BX1_BRAIN.bat`
- `STOP_BX1_BRAIN.bat`
- `BX1_DIAGNOSTICS.bat`

Old root batch files are preserved in `tools/legacy_bat/`.

## Stability behaviour

- Ollama must be available on `127.0.0.1:11434`.
- Robot Brain API runs on `0.0.0.0:8765`.
- Brain TTS service runs on `0.0.0.0:8091`.
- Robot API requests do not trigger desktop speaker playback.
- Robot TTS requests default to Chatterbox Turbo voice `chatterbox_bx1`, with service playback disabled.

## Cleaned UNO Q body client

Base snapshot: `Arduino_Q_Client_V1`.

Applied:

- `Arduino_Q_Client_V10_15_STABILITY_PATCH`
- `Arduino_Q_Client_V10_15A_STARTUP_HOTFIX`

Config defaults restored to the robot character voice route:

- `tts_backend = brain-tts`
- `brain_tts_engine = chatterbox_turbo`
- `brain_tts_voice = chatterbox_bx1`
- `brain_tts_format = wav`
- `brain_tts_timeout_s = 240`
- `brain_tts_follow_brain_host = true`

The body client starts even if the Brain App URL has not yet been configured.
