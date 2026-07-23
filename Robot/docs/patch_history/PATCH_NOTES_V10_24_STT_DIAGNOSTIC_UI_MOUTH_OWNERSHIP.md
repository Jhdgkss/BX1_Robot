# BX1 v10.24 Patch Notes

- Replaced fixed-duration STT diagnostic recording with production ALSA endpointing.
- Added pre-roll, post-roll, adaptive thresholding, speech-start confirmation and end-silence controls.
- Added raw, filtered and exact-submitted diagnostic WAVs.
- Rebuilt the body web interface around subsystem status, fault finding and control ownership.
- Removed duplicate body UI controls for Brain-owned personality/content functions.
- Enforced Brain ownership for web/memory policy, TTS voice, thinking speech and autonomous spoken dialogue.
- Kept microphone/DSP, physical hardware, safety, servo calibration and LED animation body-owned.
- Added direct MCU mouth LED RPC and brightness/command telemetry.
- Added safe config migration that preserves calibrated installation settings.
