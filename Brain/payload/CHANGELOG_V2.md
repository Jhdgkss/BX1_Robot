# Robot Brain V2.10.0 — Brain-Owned Wake and Queued Body Speech

- Makes the active desktop Brain profile authoritative for the physical robot name, wake phrase templates, aliases and wake sensitivity.
- Adds **Body Wake / Queued Speech** to the Brain interface with Save Definitions, Generate Phrase, Generate All, Test Selected and Refresh controls.
- Generates wake acknowledgements, reply-waiting phrases and the sleep acknowledgement with the active Brain voice profile.
- Publishes `/api/body_profile`, `/api/body_audio/<filename>` and `/api/body_audio/generate` for the UNO Q Body client.
- Provides SHA-256 metadata, generated/stale state and atomic phrase-library updates so changed wording cannot silently reuse old audio.
- Publishes the first-cue delay, repeat interval and maximum waiting-phrase count to the Body client.
- Preserves the existing chat, Faster-Whisper, Dot.TTS, memory, documents and web-research behaviour.

# Robot Brain V2.9.0 — Web Research and Silent Sources

- Broadens automatic internet research beyond obvious “latest”, weather and news prompts. Stable factual, explanatory, comparison and technical questions can now use live web evidence when it improves the answer.
- Keeps greetings, creative-writing requests, local-document commands and physical robot movement commands off the web route.
- Preserves local memory and relevant uploaded-document retrieval alongside general web research, rather than replacing them.
- Adds structured source extraction from web, RSS, weather and aviation contexts.
- Appends a deterministic **Sources (not spoken)** footer to the on-screen response and Robot Brain API `reply` field.
- Adds a clean `answer` field and structured `sources` array to `/api/chat` responses.
- Removes source footers, citation markers, attribution phrases and URLs from the TTS payload, desktop voice playback, robot WAV generation, speech chunks and repeat-last speech.
- Adds Live Tools controls for general web research, on-screen source display and optional source speech. Source speech is disabled by default.
- Keeps current-data fail-closed protection: when a current/news/weather lookup is required and cannot be verified, BX1 says the lookup failed instead of inventing an answer.
- Retains the V2.8.2 audio edge protection settings.

# Robot Brain V2.8.2 — Audio Edge Protection

- Adds 250 ms of silence before every Dot.TTS WAV so USB/HDMI audio devices and amplifier enable lines are ready before the first phoneme.
- Adds 400 ms of silence after speech so the final phoneme is not lost when playback or the amplifier releases.
- Adds a 4 ms edge fade to suppress clicks without trimming generated speech.
- Embeds the protection in the WAV itself, covering Brain-PC playback and robot-body `/api/audio` playback.
- Exposes the applied padding and raw/protected duration in Dot.TTS response metadata.

# Robot Brain V2.8.1 — Multi-Personality Edition

## V2.8.1 saved personality library

- Adds several named personalities inside each physical robot profile.
- Imports the existing character as **Current Personality** without changing it.
- Adds **Curious Female Companion** as a second ready-to-load personality rather than requiring another robot profile.
- Supports load, save changes, save as new, duplicate, rename and delete from the Identity / Personality page.
- Persists a personality's character name, prompt, sliders, emotional delivery and selected voice profile.
- Preserves robot connections, API ports, hardware settings, safety limits, memory, documents, Dot.TTS service state and voice recordings when switching.
- Stores an accepted self-chosen name inside the active personality so it returns when that character is reloaded.
- Uses an atomic profile-specific JSON store and prevents deletion of the final remaining personality.

## V2.8.0 deliberate expression and self-naming

- Adds hidden per-reply delivery states: normal, warm, playful, amused, excited, cautious, reassuring and serious.
- Converts the selected state into an optional natural-language Dot.TTS performance direction without exposing routing tags in chat or the robot API.
- Labels inline Dot.TTS directions as experimental and provides a Voice-page switch to disable them if a model reads the instruction aloud.
- Adds a Curious Female Companion profile preset with high curiosity, warm humour, mild sarcasm and restrained context-aware flirtiness.
- Keeps facts and safety first; flirtation is suppressed for diagnostics, engineering safety, distress, conflict and serious work.
- Adds a human-like character mode that avoids routine robot/AI self-description while remaining honest when directly asked about system architecture.
- Lets an unnamed character propose one feminine name and explain her choice; the name is saved only after explicit approval.
- Keeps existing BX1 and Leo identities unchanged unless the user deliberately edits their active profile.
- Uses a female Edge fallback for the female preset; Dot.TTS still requires a suitable profile-owned female reference recording for a consistently female cloned voice.

## V2.7.1 robot audio bridge and layout hotfix

- Publishes completed Dot.TTS WAV files through the normal Robot Brain API so the physical robot does not need direct access to WSL or port 8092.
- Advertises the v10.35 body-audio contract through `/api/status`.
- Keeps Edge-generated robot audio on the same `/api/audio/<filename>` route.
- Fixes the Voice page at shorter window heights and non-default Windows DPI scaling by using a minimum-size scroll container instead of compressing form rows.
- Opens the last-selected robot directly in the main application; no profile program appears before it.
- Runs the Profile Manager inside the existing Qt process and restarts only when the user confirms a profile switch.
- Applies Glass Blue translucency and Windows 11 Mica to the real main window, not only the profile utility.
- Corrects clipped combo boxes, spin boxes and form controls by giving them consistent minimum geometry.
- Uses one shared persistent Dot.TTS model on port 8092 for all robots while preserving profile-specific reference recordings and transcripts.
- Keeps the shared GPU service alive after Robot Brain closes and adds an explicit **Stop Voice Service** action.
- Removes optional YOLO/OpenCV packages from first-run core setup; `INSTALL_OPTIONAL_VISION.bat` installs them when required.

## V2.6.0 PyQt profile experience

- Replaces the standalone bootstrap GUI with PyQt6 so the entire desktop experience uses one interface framework.
- Adds translucent glass panels, gradient lighting, polished robot cards, improved validation and a subtle launch animation.
- Enables the documented Windows 11 Mica system backdrop with a graceful painted fallback when unavailable.
- Makes existing robot selection, ports, identity, personality and profile isolation easier to understand.
- Fixes first-run setup so dependency installation never launches BX1 before the Profile Manager.
- Centralises Windows environment preparation in `scripts/INSTALL_CORE.bat` and adds regression coverage for the startup flow.

## V2.5.1 compatibility hotfix

- Fixes Profile Manager startup on Tk builds that misparse `Segoe UI` tuple fonts and report `expected integer but got "UI"`.
- Uses persistent named Tk font objects for the application default, headings, buttons and titles.
- Adds a regression test that prevents raw tuple fonts from returning to the Profile Manager.

## Voice platform replacement

- Makes Dot.TTS the primary robot voice.
- Starts the WSL2 service automatically after the GUI appears.
- Adds background readiness checks, progress messages and optional model warm-up.
- Stops only a Dot.TTS service instance started by Robot Brain.
- Keeps manual MF and SOAR launchers for testing and diagnostics.
- Adds Edge as the only fallback for desktop speech and robot API audio.
- Adds safe Brain-hosted `/api/audio/<filename>` delivery for fallback MP3 files.
- Isolates Dot.TTS reference audio and transcripts per robot profile; BX1's tested reference is included while new robots start clean.
- Replaces the crowded voice page with focused Dot.TTS, Edge, health, lab, tuning, test and save controls.
- Removes the superseded Windows voice service, installers, dependency locks, package requirements and profile-specific service configuration.

## Preserved V2.4 improvements

- Drag-and-drop and Open File reference upload in the English Voice Lab.
- Current-text and fixed short/medium/long performance benchmarks.
- Runtime signature filtering for changing Dot.TTS generation APIs.
- Active reference-audio/transcript reuse between Voice Lab and Robot Brain.
- Safe Windows-to-WSL path handling.
- Relevance-gated local-document retrieval and live-data truthfulness safeguards.
- Independent robot identity, personality, API ports, configuration and runtime storage.
