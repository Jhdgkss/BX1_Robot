# BX1 / Robot Body Client Patch V8.9 - Robot Profile, Personality, Themes

This patch makes the Arduino Q body client more reusable across different robots.

## Added

- Local robot profile support using `python/robot_profile.json`.
- The profile is created automatically on first run from your current `python/config.json` if it does not already exist.
- New **Robot Profile** page in the web UI.
- Editable robot name, display name, wake words, personality summary, tone, humour level, confidence level, verbosity, rules, robot type, location and capabilities.
- Robot profile is attached to telemetry, chat, camera-frame and vision payloads.
- Colour theme selector in the web header.
- Themes: Dark Blue / BX1, Graphite, Workshop Green, Amber Console, Purple Lab and Light.
- TTS playback device is now part of the speech settings and robot voice profile.
- TTS players can use a fixed ALSA output such as `plughw:1,0` instead of relying on the Linux default sound card.

## Why this matters

The same body-client software can now run on BX1, BX2 or another robot without hard-coding the identity/personality into the Python code. Each robot owns its own local profile.

## Laptop Brain App note

This Arduino Q patch is backward-compatible, but the laptop Brain App should also be updated so it actually reads `robot_profile` and uses it when building the LLM system prompt. Until then, the profile is sent but may be ignored by the laptop app.
