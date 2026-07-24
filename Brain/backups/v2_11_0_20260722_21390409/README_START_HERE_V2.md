# Robot Brain V2.8.1 — Start Here

This complete release keeps every robot's identity, personality, configuration and runtime data separate. Dot.TTS is the primary voice engine; Edge is the lightweight fallback.

For speech on the physical BX1 speaker, use **BX1 Body Client v10.35 or newer**. The body requests one generated reply WAV from the Brain API, plays it locally with mouth animation, and no longer connects to a separate voice port.

V2.8.1 opens the main PyQt6 application directly on the last-selected robot. Profile management runs inside Robot Brain, and the actual main window uses translucent Glass Blue panels with Windows 11 Mica when available.

## Saved personality library

Open **Robot → Identity / Personality**. Every robot starts with two saved choices: **Current Personality**, imported from the settings already in use, and **Curious Female Companion**. Select one and press **Load Selected**. You can then save changes, save a new personality, duplicate, rename or delete personalities without creating another physical robot profile.

A personality stores its character name, identity style, gender, prompt, sliders, emotional delivery choices and selected voice profile. Robot API settings, hardware limits, memory, documents and voice recordings remain owned by the physical robot profile and are not duplicated or deleted by personality switching.

When Curious Female Companion is loaded for the first time, the character proposes one name for herself. Robot Brain shows the proposal and reason, then stores the accepted name inside that personality only. Switching away and back restores it.

The preset is curious, warm, funny, mildly sarcastic and only lightly flirty in relaxed conversation. It suppresses flirting and jokes for safety, diagnostics, distress and serious engineering work. It also enables experimental natural-language Dot.TTS delivery directions. Turn that Voice-page option off if Dot.TTS speaks the direction itself.

The preset uses `en-GB-SoniaNeural` as its Edge fallback. For a consistent cloned female Dot.TTS voice, open **Voice Lab** while that personality is active, upload a clean female reference WAV with its exact transcript, select it, then press **Save Changes** in the personality library. Voice recordings remain isolated to the physical robot profile.

## Start Robot Brain

Double-click **`START_ROBOT_BRAIN.bat`**. The main application opens directly using the last-selected robot. Use **Robot Profiles** inside the main window to create or switch robots.

On first launch the Windows Python environment is created automatically. Robot Brain then starts one shared Dot.TTS service in WSL2, waits for it, and warms the selected model once. The service remains resident after Robot Brain closes, so later launches and profile switches reuse the warm GPU model.

## First-time Dot.TTS setup

1. Run **`INSTALL_DOT_TTS.bat`** once.
2. Run **`CHECK_DOT_TTS_WSL.bat`** and confirm `dots_tts: OK` and `CUDA: True` when using an NVIDIA GPU.
3. Start Robot Brain and open **Robot → Voice → Open Voice Lab**.
4. Drop or select a clean reference recording and enter its exact transcript.
5. Generate one successful sample. That tested reference pair becomes the active cloned voice.
6. Press **Save Voice Settings** in Robot Brain.

The MF model is the recommended fast default at four sampling steps. SOAR is available for comparison. The first model load can take several minutes; later generations are much faster.

Manual launchers remain available for diagnostics:

- `START_DOT_TTS_MF.bat`
- `START_DOT_TTS_SOAR.bat`

If Dot.TTS cannot start or generate a reply, Robot Brain automatically uses the configured Edge voice for that reply. Edge runs on Windows and does not need a local model. Use **Stop Voice Service** only when you deliberately want to release GPU memory; the next start will be slower.

## Independent robot profiles

Each profile owns:

- `config/app_config_<profile>.json`
- `config/secrets_<profile>.local.json` when required
- `runtime/<profile>/` for documents, audio, images, logs and other profile data
- `runtime/<profile>/dottts/` for its active cloned-voice reference metadata and Lab uploads
- `config/personality_profiles_<profile>.json` for that robot's saved personality library

The selected robot name, physical description, personality prompt, personality sliders, voice reference and Brain API port remain configurable. A newly created robot starts with an empty voice reference rather than inheriting BX1's recording. All profiles share Dot.TTS on port 8092 while sending their own reference audio and transcript with each request.

BX1's tested starter reference is stored as a deliberate project asset under `assets/voices/bx1/`. Generated speech, uploaded references, memories, manuals and logs are runtime data and are not bundled into the clean release.

## Interface map

- **Overview:** chat, status cards and quick setup.
- **Robot:** identity, personality, voice and internet tools.
- **Knowledge:** local documents and memory.
- **Behaviours:** bounded behaviour design and human approval.
- **Hardware:** telemetry, camera and robot actions.
- **System:** diagnostics and maintenance.
- **Preferences:** models, API and appearance.
- **Help:** setup and troubleshooting guidance.

## Local documents and live sources

Document retrieval is relevance-gated. Greetings and live news/weather/web questions do not pull unrelated manuals into the answer. Technical questions and explicit `/docs`, `/document`, `/manual` or `/rag` requests can use the document library. Manuals are reference material, not proof of a current robot fault.

## Safety

The Arduino/body controller must continue to own balance, motor limits, collision stops and emergency shutdown. The Brain may request actions but must not bypass body safeguards.

## Recovery tools

- `BX1_DIAGNOSTICS.bat` — Windows, Ollama, Brain API and Dot.TTS checks.
- `CHECK_DOT_TTS_WSL.bat` — detailed WSL2, NVIDIA, PyTorch and Dot.TTS diagnostics.
- `REPAIR_BX1_PYTHON_ENVIRONMENT.bat` — rebuild the Windows application environment without touching WSL2.
- `INSTALL_OPTIONAL_VISION.bat` — add the large optional YOLO/OpenCV packages only when object detection is required.
- `STOP_BX1_BRAIN.bat` — stop BX1 and request a graceful Dot.TTS shutdown.
- `docs/ARCHITECTURE.md` — technical structure and ownership.
