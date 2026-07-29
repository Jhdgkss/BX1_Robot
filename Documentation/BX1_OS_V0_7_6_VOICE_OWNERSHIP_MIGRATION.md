# BX1 OS v0.7.6 — Voice Ownership Migration

BX1 OS on port 8089 is the normal touchscreen/operator surface for wake and speech settings. Robot Body on port 8088 remains the sole ALSA microphone and speaker owner. The older Body speech page is retained as an engineering fallback only.

## Safe configuration boundary

The Body exposes `GET` and `PUT /api/bx1-os/voice-settings/v1`. Only these existing Body settings are accepted: `wake_words`, `wake_command_window_s`, `stt_end_silence_ms`, `mic_noise_gate_dbfs`, `stt_noise_margin_db`, `stt_adaptive_margin_db`, and the existing STT policy (`brain_faster_whisper` or `vosk`). The API validates phrase count/length and numeric ranges, then atomically replaces the existing machine-local `python/config.json` while preserving unrelated keys, owner and mode.

BX1 OS proxies this at `/api/audio/voice-settings/v1`; it does not read, write or expose arbitrary configuration or credentials.

## Non-blocking recognition

There is exactly one live ALSA capture loop. A completed immutable WAV payload enters a one-item in-memory STT/Brain worker queue. A full queue drops the new utterance and reports `STT worker queue full; utterance dropped`; it never accumulates audio work. The capture callback continues publishing bounded level heartbeat metadata while the worker is recognising or contacting the Brain.

Desktop faster-whisper is bounded to **12 seconds** (with a 2–20 second safety clamp for existing configuration). On desktop transport, service or timeout failure, the existing local Vosk recogniser promptly evaluates the same captured WAV when it is available. No raw audio leaves the Body except through the pre-existing completed-WAV Brain STT request, and no audio/transcript is written by BX1 OS to logs, exports or persistent storage.

The shared Live Voice console remains temporary RAM only, capped at 200 entries, clearable from BX1 OS and cleared on OS restart. Brain remains authoritative for conversation memory and personality.
