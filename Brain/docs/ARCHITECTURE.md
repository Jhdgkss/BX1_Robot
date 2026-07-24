# Robot Brain V2.8.1 Architecture

## Windows Brain application

`main_pyqt.py` provides the PyQt interface, robot body API, Ollama integration, live web/weather tools, local document retrieval, memory, vision, speech recognition, behaviour workshop and diagnostics.

`main_pyqt.py` reads the last-selected profile before constructing the window, so there is no separate startup surface. `tools/robot_profile_manager.py` is loaded in-process only when **Robot Profiles** is opened. A confirmed profile switch restarts the main window with the new profile. Windows 11 uses the documented Mica backdrop API; translucent Qt gradients are the cross-version fallback.

The physical robot profile owns connections, hardware-facing settings, memory, documents and voice recordings. `robot_brain/personality_store.py` provides a second profile-specific layer for saved character identities and personality settings. Switching this layer is immediate and does not restart the Brain or the shared Dot.TTS service. The Arduino/body client remains generic hardware I/O and owns physical safety.

## Voice architecture

Dot.TTS runs as one shared HTTP/GPU service inside WSL2 on port 8092. The Windows Brain starts it asynchronously, checks `/health`, warms the model only when it is not already loaded, sends text plus the active robot's reference pair to `/speak`, downloads the WAV and plays it locally.

When a body-client request includes `return_audio=true`, the Brain copies the completed WAV into its profile-owned API output directory and returns `/api/audio/<filename>`. The body downloads that file from the same Brain API host and port used for chat. WSL and port 8092 therefore remain private implementation details of the Brain PC.

The English Voice Lab at `/lab?profile=<id>` owns profile-specific reference-audio upload, transcript pairing and benchmarking. The model and output queue are shared; reference configuration remains under `runtime/<profile>/dottts/`.

Edge speech runs in the Windows application as the sole fallback. It can generate local MP3 audio for desktop playback or for the robot API at `/api/audio/<filename>`.

## Configuration and runtime

- `config/app_config_<profile>.json` stores robot, API, personality, tools and voice settings.
- `config/personality_profiles_<profile>.json` stores named character snapshots and the active personality selection.
- `config/secrets_<profile>.local.json` stores local secrets when needed.
- `runtime/<profile>/` stores profile-owned knowledge, memory, images, audio and logs.
- `runtime/<profile>/dottts/` stores that robot's Dot.TTS reference and transcript.
- `runtime/dottts_shared/` stores transient output from the shared GPU service.

The Dot.TTS Python environment and model cache remain in the Linux user's home directory. Windows application dependencies remain in `.venv`.

## Integration Hub

`bx1_integrations/` contains the modular framework for external services and robot behaviours. `main_pyqt.py` owns only the GUI wiring; credentials, HTTP calls, permissions and behaviour validation remain in integration modules.

- `base.py` defines the common integration interface, structured result/error objects and safety levels.
- `registry.py` registers integrations and exposes safe structured actions for future conversation-engine routing.
- `permissions.py` enforces READ_ONLY, CONTROL and SAFETY_CRITICAL action gates. CONTROL actions require confirmation when initiated by AI. SAFETY_CRITICAL actions require explicit confirmation every time and must never run automatically.
- `events.py` stores activity events and masks API keys, bearer tokens and OAuth tokens before logging.
- `octoprint_connector.py` implements mocked and live-ready OctoPrint status/control calls with HTTP timeouts and response-size limits. Arbitrary G-code is not exposed.
- `spotify_connector.py` implements mocked and live-ready Spotify OAuth Authorization Code with PKCE, playback state and Spotify Connect controls. Robot Brain does not download, proxy, record or stream Spotify audio.
- `dance_service.py` provides reusable choreography definitions and built-in routines. Head and LED limits are enforced; wheel movement is disabled by default.

Secrets must not be stored in Git-tracked JSON. The framework prefers OS credential storage through `keyring` when available and otherwise falls back to session-only secrets with a visible warning path in the UI.

Natural-language voice routing into the integration registry is intentionally separate work. The GUI can test the integrations in mock/demo mode now; the conversation engine should later call `IntegrationRegistry.execute(...)` and honour the same permission decisions.

## Service lifetime

The shared Dot.TTS service remains running when the Brain window closes or changes profile. This preserves the loaded and compiled model. The Voice page's explicit **Stop Voice Service** action releases it when GPU memory is needed; Edge remains the fallback while it is unavailable.

## Hardware safety

The body controller owns balance, actuator limits, range checks and emergency stops. Generated behaviours are bounded and require the configured human-approval path.
