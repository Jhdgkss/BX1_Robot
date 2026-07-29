# BX1 OS Architecture and Handoff

## Agreed architecture

- The Windows Brain desktop application is LEO's primary conversation UI. It owns
  conversation history, personality, LLM orchestration, memory, RAG and TTS.
- Robot Body is the hardware authority. It owns microphone input, wake/STT,
  speaker playback, LEDs, head, MCU and sensors.
- BX1 OS is the modular runtime: module manager, event bus, safe capability
  gateway, service supervision and local engineering interface.
- BX1 OS must not become a second Brain conversation application.
- The v0.6.1 **Talk to Leo** field is an engineering Body → Brain → TTS
  smoke-test, not the future primary chat UI.
- The Robot Body page on port 8088 remains a temporary engineering fallback
  while its capabilities are extracted behind safe APIs.

## Current live state

| Component | State |
|---|---|
| Robot Body | Original v10.39 identity on port 8088, with the approved v0.6.1 voice Body patch. |
| BX1 OS | v0.6.1-development voice conversation on port 8089; manually started and intentionally not enabled at boot. |
| Brain | Windows desktop application at `192.168.68.53:8765`. |
| Typed route | Body → Brain chat/LLM → Brain TTS → Body speaker playback works end-to-end. |
| Spoken route | Wake route works. Brain Faster-Whisper/STT requests have timed out and Body falls back to local Vosk; improving this is a future voice-quality task. |

## Next milestone: BX1 OS v0.7 — Modular Runtime Developer Preview

- Module manifest, loader, lifecycle and health model.
- Bounded event bus and safe permissions/capabilities.
- Module Manager web page.
- Scaffold tool and developer guide.
- One non-hardware `speech_indicator` example module.
- No direct motor, balance, raw MCU, raw servo or raw camera access.

## Development workflow

This is a hobby-project pace: build a feature, run one focused check, deploy
with a backup, then perform one real smoke test. Repeat formal validation only
when a check or smoke test fails.

## Relevant branch and commits

- Branch: `feature/bx1-os-v0.6-voice-vertical-slice`
- v0.6 voice vertical slice: `d5def4ee56d604db3df5e6dff4d1b8753ff8c4c5`
- v0.6.1 voice interaction repair: `7887e192e92e3a9af8ad3463133152516eb5a4e6`
