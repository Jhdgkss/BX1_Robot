# BX1 / Robot Body Client Patch V9.0 - Main STT, Camera-Aware Chat, Brain-App Internet Route

This patch builds on V8.9 and keeps the robot body client reusable for different robots.

## Added

- Main Chat page now includes quick STT controls:
  - Enable live microphone/STT loop.
  - Select main input mode.
  - Listen Once.
  - Listen Once + Send.
- Main Chat page now includes web/camera defaults:
  - Allow laptop Brain App internet/web for this message.
  - Use memory/context.
  - Auto use camera when asked.
  - Save Web/Camera Defaults.
- New `/api/stt_once` endpoint:
  - Records a short microphone sample.
  - Runs Vosk STT.
  - Optionally sends the recognised text directly to the Brain App.
- New `/api/chat_settings` endpoint:
  - Saves default web-search routing.
  - Saves camera auto-trigger behaviour.
  - Saves vision trigger phrases.
- Camera-aware chat routing:
  - Prompts such as "what can you see", "look at this", "what is this", "what am I holding", and "use your camera" are automatically routed to the Brain App vision endpoint.
  - Vision requests can now pass the `use_web` flag to the laptop Brain App.
- Telemetry now includes a `network` block explaining that internet lookup should happen via the laptop Brain App, not the Arduino Q.

## Changed

- The web UI version is now V9.0.
- The service reports `RobotBodyClient/0.9.0`.
- The main window can now be used for normal keyboard, one-shot speech, and continuous STT setup.

## Important laptop Brain App note

This patch makes the Arduino Q send clearer information to the laptop Brain App, including robot profile, use-web requests, and camera/vision requests. The laptop app should also be updated so it:

1. Always consumes `robot_profile` and uses it in the LLM system prompt.
2. Honours `use_web=true` by using the laptop's internet/web-search tools.
3. Honours `/api/vision` requests with the camera image and optional web lookup.
4. Optionally supports a future tool-call style action such as `request_camera_view`.

The Arduino Q does not need direct internet access for LLM web lookup. It should ask the laptop Brain App to do that work.
