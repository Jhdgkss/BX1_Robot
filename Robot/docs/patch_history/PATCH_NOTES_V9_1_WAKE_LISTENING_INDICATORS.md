# V9.1 Wake / Listening Indicators Patch

This patch builds on V9.0 and adds clear live feedback for the speech wake-word loop.

## Added

- Main Chat page now has a live **Voice / Wake Status** panel.
- Animated orb/status indicator for:
  - Voice disabled
  - Starting STT
  - Listening for wake word
  - Speech heard
  - Heard but ignored
  - Robot awake
  - Processing Brain App request
  - Voice/STT error
- Top status pills now include a `voice:` status.
- Shows recent diagnostics:
  - Last heard phrase
  - Last wake word
  - Last accepted command
  - Wake words currently being used
- Voice loop now logs `wake word detected` events in the Conversation / Event Log.
- `/api/status` now includes `voice_runtime` and `state.mic.runtime`.

## Intended test

1. Open **Chat / Debug**.
2. Tick **Enable live microphone/STT loop**.
3. Set mode to **voice or keyboard**.
4. Press **Save Main STT Settings**.
5. The indicator should change to **Listening for wake word**.
6. Say: `Robot, what is your name?`
7. The indicator should briefly show **Robot awake**, then **Awake and processing**, then return to listening.

## Notes

- This does not change the Brain App protocol.
- This does not change speech output/TTS settings.
- This does not overwrite `python/config.json` or `python/robot_profile.json`.
