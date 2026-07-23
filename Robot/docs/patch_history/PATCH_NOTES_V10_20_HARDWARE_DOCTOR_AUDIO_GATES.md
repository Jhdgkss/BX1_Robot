# BX1 UNO Q Body Client v10.20

## Hardware Doctor, speech acceptance gates and live audio filtering

This is a complete overwrite update for the UNO Q Linux body client and the MCU sketch.

### Unsolicited conversation protection

Every microphone event now receives an event ID and provenance record before it can reach the desktop Brain. The body rejects:

- empty or filler-only Vosk fragments;
- speech below the configured voiced-duration limits;
- low-confidence Vosk transcripts;
- near-duplicate transcripts received inside the duplicate window;
- transcripts that closely match BX1's own recent speech;
- wake-word substring accidents.

Idle micro-movements remain enabled, but `idle_life_self_chatter_enabled` and internet curiosity are disabled by default. This prevents idle behaviour from silently entering the normal user conversation pipeline.

### Audio processing

The microphone path now supports a real-time, dependency-light DSP chain:

1. software input gain;
2. 90 Hz high-pass filter by default;
3. 50 Hz mains notch with optional harmonics;
4. soft noise reduction / expander;
5. voiced-duration and Vosk confidence validation.

The microphone page displays raw and filtered RMS levels and a live raw-versus-filtered FFT. The filters are adjustable and saved in `python/config.json`.

This release does **not** claim full acoustic echo cancellation. It uses TTS microphone hold-off plus transcript similarity rejection, which is safer on the current USB webcam / Debian audio arrangement. A proper far-end-reference AEC stage can be added later after the actual microphone and loudspeaker routing is measured.

### Hardware Doctor

Hardware Doctor performs deterministic checks of:

- the `arduino-router` Unix socket;
- router service status;
- MCU status RPC availability;
- firmware, protocol and build identifiers;
- maintenance mode;
- availability of compile/upload tools.

Its only automatic repair authority is restarting the allow-listed `arduino-router` service after repeated failures and a cooldown. It cannot execute arbitrary shell commands.

Hardware Doctor can generate fixed, review-only diagnostic sketches for bridge, heartbeat and IMU testing. Generated manifests always start with `approved=false`, `compiled=false` and `flashed=false`. Autonomous compilation and flashing are disabled.

### MCU sketch v10.20

The MCU now reports firmware version, protocol version, build ID, heartbeat sequence, maintenance mode, drive-output state and command age. It adds bounded `bx1_ping` and `bx1_set_maintenance_mode` RPCs. Maintenance mode blocks drive requests and stops current motion.

### Install on the UNO Q

1. Back up `/home/arduino/Arduino_Q_Client_V1/python/config.json` and `python/robot_profile.json`.
2. Stop the running service: `sudo systemctl stop bx1-web.service`.
3. Replace the project folder with this complete `Arduino_Q_Client_V1` folder.
4. Restore only any site-specific settings that are not already in the supplied configuration.
5. Run `chmod +x START_BX1_WEB.sh STOP_BX1_WEB.sh tools/*.sh`.
6. Start with `./START_BX1_WEB.sh` or `sudo systemctl restart bx1-web.service`.
7. Open `http://BX1.local:8088`, confirm the microphone page and run Hardware Doctor.
8. Review and compile the MCU sketch manually before flashing. Do not enable drive outputs during this diagnostic stage.

### Recommended first test

Leave the robot silent for two minutes with the microphone monitor running. The input event log should show rejected noise events rather than new LLM replies. Then speak a normal sentence and confirm a single accepted `VOICE` event appears.
