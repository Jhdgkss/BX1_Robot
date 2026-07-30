# BX1 OS v0.8 voice controls

The Robot Body owns capture, configured wake phrases, STT submission and speaker playback. A shared speaker-active gate closes the microphone during every playback route, discards recognition frames, waits for `speaker_echo_tail_ms`, flushes buffers, and then reopens wake/listening.

The body exposes `/api/audio_controls`, `/api/speech_scan`, and `/api/documentation` locally. Privacy mute is a hard, recoverable control from the web/touch UI; listening pause suspends wake processing; speaker mute and Stop Speaking are separate controls.

Speech scan is diagnostic context only. `request` is the only text sent to Brain. Highlight ranges identify the exact wake phrase and extracted request. Diagnostic audio retention remains bounded by the existing capture settings and should be cleared/exported by operators.

Themes and robot identity are separate. Custom themes are persisted in the body config; profiles provide robot name, display name, logo/avatar, wake phrases, personality identifier and response voice. Repository Markdown remains the offline documentation source rendered by the UI.

For local validation run the focused voice tests under `Robot/tools`. Deploy through the existing package/SSH workflow, back up only replaced files, restart the web and voice services, and keep the prepared rollback package available.
