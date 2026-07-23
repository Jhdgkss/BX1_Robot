# Changelog

## 10.42

- Fixed the Brain connection editor being overwritten by the 1.25-second status refresh while the user was typing.
- Replaced the single URL field with separate protocol, Brain host/IP and port controls.
- Added validation for ports 1–65535 and retained the chosen port when using **Use this browser PC**.
- Added current Robot Body and Brain endpoints to the Advanced page.
- Added Robot Body and Brain IP:port information to the onboard touchscreen.
- Constrained both web interfaces to the physical viewport and added safe edge insets to prevent right-side clipping.
- Forced Chromium kiosk device scale factor to 1 for consistent touchscreen sizing.
- Preserved MCU firmware, Modulino Movement, servos, LEDs, shared microphone and Brain-owned wake/queued-speech features.

## 10.41

- Added a dedicated portrait onboard touchscreen display.
- Added a compact runtime endpoint containing heard text, full responses, service health and telemetry.
- Added kiosk browser autostart, screen wake settings and optional display/touch rotation.
- Added automatic-login configuration for common Debian display managers.
- Preserved all hardware safety ownership and existing Brain/profile settings.

# v10.40 — Brain Profile Wake, Shared Audio and Queued Speech

- Replaces competing microphone owners with one permanent ALSA capture stream shared by wake detection, level display, diagnostic recording and production STT.
- Removes the normal `microphone is busy` handover path and gives every subscriber bounded start/end timeouts.
- Uses local constrained Vosk grammar recognition for wake phrases supplied by the active desktop Brain profile.
- Keeps a 600 ms overlap between short wake windows so phrases are not lost at a window boundary.
- Continues the same audio stream after wake detection and sends the complete command to Brain Faster-Whisper.
- Synchronises the robot name, wake templates/aliases, wake sensitivity and queued speech definitions from `/api/body_profile`.
- Caches the last valid Brain profile for offline startup and adds a manual **Sync Brain profile now** action.
- Downloads Brain-generated wake acknowledgements, waiting phrases and sleep acknowledgement into the UNO Q local cue cache with SHA-256 verification.
- Invalidates stale local cue audio immediately when its Brain-owned wording changes.
- Keeps wording and first/repeat/max cue timing Brain-owned; the Body only owns playback, endpointing and safety controls.
- Does not compile, upload or change the working v10.39 MCU firmware. Servo quiet mode, RouterBridge, Modulino Movement, LEDs and disarmed RS485 scaffolding are preserved.

# v10.39 — 2026-07-21

- Added cooperative ALSA capture cancellation so the live wake listener yields to **Listen once** within one audio frame.
- Prevented the level-meter process reopening during a microphone handover race.
- Replaced the generic `microphone is busy` failure with a bounded handover timeout and clearer evidence.
- Added quiet-servo release after movement, automatic reattach, pulse deadband and status telemetry.
- Added Hardware-page controls for servo release delay and deadband.
- Preserved user microphone gain/noise-gate settings during migration.
- Kept wheel outputs disabled and unarmed.

# v10.38 — 2026-07-21

- Fixed v10.37 MCU RouterBridge timeout.
- Updated Arduino_RouterBridge from 0.4.2 to 0.4.3.
- Forced clean Arduino App Lab sketch build by clearing the app-specific cache.
- Registered BX1 RPC endpoints before hardware discovery.
- Deferred servo, LED and Movement initialisation until the bridge is online.
- Probed Modulino Movement at both 0x6A and 0x6B.
- Added bootstrap ping verification and automatic failure diagnostics.
- Preserved MicroPython architecture files and kept wheel outputs disarmed.

# BX1 Robot Body Client v10.37

## MCU bridge and Modulino Movement

- Persistent UNO Q App Lab MCU runtime and Router RPC verification.
- Modulino Movement on `Wire1/Qwiic` at `0x6A` with retry and telemetry evidence.
- Correct separation of MCU connectivity and IMU health.
- Hardware page repair details and Hardware Doctor IMU diagnosis.
- D9/D10/D11 mixed head servos and D3 LED registry preserved.
- Wheel output disabled, unarmed and protocol-gated.
- Modular MicroPython reference bundle included.

# BX1 Robot Body Client v10.36

## Audio capture identity and stale-WAV correction

- Gives every STT diagnostic capture a unique ID and unique raw, filtered and submitted WAV filenames.
- Playback buttons remain disabled until the current capture has completed.
- Browser playback uses the returned capture-specific URL plus cache busting.
- Legacy fixed filenames are published atomically only for compatibility.
- Adds no-cache, pragma and expiry response headers and exposes the served capture ID.

## Faster speech recognition path

- Reuses the already-loaded Vosk model instead of rebuilding it for every diagnostic test.
- Defers local Vosk decoding while desktop Brain faster-whisper is available.
- Runs local Vosk only if the Brain STT transport/service fails.
- Reports Brain round-trip, local recognition and complete STT pipeline timings separately.

## Endpointing correction

- Uses endpoint hysteresis and a sustained-speech resume test after established silence.
- Short clicks, chirps and handling spikes no longer restart the full end-silence timer.
- Adds a safe migration to 600 ms end silence, 160 ms post-roll and a 5 dB adaptive margin when older slower values are present.

# BX1 Robot Body Client v10.35

## Installer validation correction

- Release checks now validate only files owned by v10.35, so historical patch
  scripts retained in an upgraded target cannot cause a false failure.
- A failed update removes v10.35-owned files before restoring the rollback
  archive, preventing a mixed old/new program tree.

## Installer reliability correction

- Replaced the unbounded full-project gzip backup with a fast, bounded rollback backup.
- Diagnostic traces, old update payloads, runtime data, models and existing archives are no longer recompressed.
- Backup progress is shown every few seconds.
- The rollback archive is written to a temporary file and validated before installation begins.
- Interrupting the backup no longer attempts to restore from a partial archive.

- Requests generated reply audio with normal Brain chat and vision calls.
- Downloads `/api/audio/<filename>` from the same Brain API address used for chat.
- Plays Brain-provided WAV or MP3 replies on the robot and retains mouth-envelope events.
- Uses the local lightweight voice only for acknowledgements and failed/missing reply audio.
- Extends Brain request timeouts so a cold Dot.TTS start does not prematurely fail.
- Migrates older configurations while preserving hardware maps, calibration, microphone, speaker and API settings.
- Adds a dated backup, automatic rollback and offline release checks to the updater.
- Removes the retired voice engine and old separate voice-port assumptions.
- Does not change or flash the Arduino/MCU sketch.
