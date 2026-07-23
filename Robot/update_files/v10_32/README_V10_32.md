# BX1 Body Client v10.32 — Wake, Thinking and Live Status

This update fixes the robot-side causes of missed wake words and silent/stale thinking feedback.

- Adds dynamic faster-whisper wake hints and preserves the wake phrase in the transcript.
- Uses the local Vosk transcript as a secondary wake-word detector when Whisper omits the first word.
- Adds aliases and bounded fuzzy matching for Hello/Hey/Robot/Leo/BX1.
- Increases audio pre-roll and makes the speech-start threshold less aggressive.
- Returns thinking-cue ownership to the robot body: chirp first, then a cached/local spoken cue for slow replies.
- Records whether the thinking audio actually played and shows any playback error.
- Keeps the web status refreshing even when a settings field or chat box has unsaved text.
- Adds a bounded Brain-request watchdog and separate HTTP connect/read timeouts.

No MCU firmware is flashed. Existing Brain address, microphone, speaker, voice and wake-word settings are preserved.
