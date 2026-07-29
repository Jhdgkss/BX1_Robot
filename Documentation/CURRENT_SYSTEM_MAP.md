# Current System Map

This map describes the active source tree, not a proposed replacement.

## Current architecture and handoff — 2026-07-29

- Brain desktop application is the primary conversation UI and owns history,
  personality, LLM, memory, RAG and TTS. The verified current Brain endpoint is
  `192.168.68.53:8765`.
- Robot Body remains the hardware authority for microphone, wake/STT, speaker
  playback, LEDs, head, MCU and sensors. Its engineering fallback page remains
  on port 8088 while capabilities are extracted behind safe APIs.
- BX1 OS is the modular runtime, module manager, event bus, safe capability
  gateway, service supervision and local engineering interface. It must not
  become a duplicate Brain conversation application.
- BX1 OS v0.6.1-development voice conversation runs on port 8089, is manually
  started and intentionally not enabled at boot. The Talk to Leo field is an
  engineering Body → Brain → TTS smoke test, not the future chat UI.
- Typed conversation works end-to-end. The spoken wake route works, but Brain
  Faster-Whisper/STT requests can time out and Body falls back to local Vosk;
  this is a future voice-quality task.
- The next milestone is BX1 OS v0.7 Modular Runtime Developer Preview: bounded
  event bus, module lifecycle/health, safe capabilities, Module Manager,
  scaffold/developer guide and a non-hardware `speech_indicator` example. No
  direct motor, balance, raw MCU, raw servo or raw camera access.

| Responsibility | Actual implementation |
|---|---|
| Robot startup | `Robot/main.py` compatibility wrapper runs `Robot/python/main.py`; `BX1RobotBodyService` owns the runtime. |
| Robot launchers | `Robot/START_BX1_WEB.sh`, `Robot/tools/run_robot_body.sh`; systemd units are `Robot/service/bx1-web.service` and `Robot/service/bx1-robot-body.service`. |
| Brain startup | `Brain/START_BX1_BRAIN.bat` launches `Brain/main_pyqt.py`; `main()` creates the PyQt application. |
| Voice capture | `Robot/python/audio_io.py`: `record_microphone_sample`, `record_microphone_utterance`, `AlsaMicrophoneMonitor`, and `VoskSpeechToText`; `arecord` is the preferred ALSA path. |
| Speech output | `Robot/python/audio_io.py`: `TextToSpeech` worker and backend methods; Brain Dot.TTS service is `Brain/bx1_services/dottts_service/app.py`. |
| Wake detection | `Robot/python/main.py`: `BX1RobotBodyService.voice_loop`, wake matching/diagnostic helpers and conversation-window state. |
| Servo movement | Linux validation/configuration in `Robot/python/main.py` and `hardware_bridge.py`; MCU mixing, clamping and PWM in `Robot/sketch/sketch.ino` (`configureServo`, `applyHeadPose`, `bx1_set_head_pose`). |
| LED output | State/envelope selection in `Robot/python/main.py`; transport in `hardware_bridge.py`; MCU NeoPixel zone functions in `Robot/sketch/sketch.ino`. |
| IMU access | MCU `Arduino_LSM6DSOX` direct instances on `Wire1` at `0x6A`/`0x6B` in `Robot/sketch/sketch.ino`; Linux observes fields through `BX1HardwareBridge.get_status`. |
| Robot web API | `Robot/python/web_control.py`: `WebControlServer`, a `ThreadingHTTPServer` with `/api/*` routes. |
| Brain API | Embedded API in `Brain/main_pyqt.py`; Robot client routes are centralized in `Robot/python/bx1_robot_client.py` (`status`, `stt_status`, `transcribe_wav`, `send_body_state`, `chat`, `vision_frame`, `command_ack`). |
| Configuration | Robot `Robot/python/config.json` and `robot_profile.json` are machine-local, ignored runtime state created from the tracked `config.example.json`/`config.fresh.json` schemas; startup options remain in `Robot/python/main.py`. Brain configuration is under `Brain/config/app_config_*.json`, with personality and robot-profile JSON files. |
| Logging/telemetry | Robot stdout/systemd journal plus event buffers and `/api/status`; MCU `bx1_get_status`; Brain UI logs and telemetry panels in `main_pyqt.py`. |
| Diagnostics | `Robot/python/hardware_doctor.py`, `Robot/tools/check_*`, `desktop_api_smoke_test.py`, `COLLECT_BX1_VOICE_TRACE.sh`, and Brain `BX1_DIAGNOSTICS.bat`. Phase-one tools add `audio_noise_diagnostic.py` and `imu_diagnostic.py`. |
| Deployment | Robot install/update shell scripts, `tools/install_on_uno_q.sh`, service installers and MCU compile/upload scripts; Brain apply/install batch and PowerShell scripts plus robot release builder. |

## Process, thread and asynchronous boundaries

- Brain is one GUI process with Qt workers, background Python threads, embedded
  API service and optional separate Dot.TTS process.
- Robot is one main Python body process. It starts the threaded web server, TTS
  queue worker, voice/camera/telemetry and feedback workers.
- Each Robot web request is handled by `ThreadingHTTPServer`.
- Linux-to-MCU Router transactions are serialized by locks in
  `RouterRpcClient`; serial fallback has its own lock.
- MCU RPC handlers store bounded work; the Arduino `loop()` performs hardware
  updates and samples the IMU.
- systemd can start the Robot body/web runtime independently of an SSH shell.

## Existing movement state

`Robot/mcu_micropython/` is a documented reference architecture, not the active
deployed runtime. It includes a disabled RS485 wheel abstraction and safety model.
The active Arduino sketch accepts abstract motion fields but the current hardware
registry keeps the drive bus disarmed; no Makerbase protocol is commissioned.

## Historical `ready_no_imu` finding

The legacy copy `Robot/files/sketch/sketch.ino` includes `Arduino_LSM6DSOX.h` but
uses the library's global `IMU` object and calls `IMU.begin()` during `setup()`.
That global object uses the default `Wire` bus. The external Modulino Movement is
on UNO Q Qwiic `Wire1`, so initialisation could not see it and the sketch set
`modeText = "ready_no_imu"` while leaving the bridge operational.

The active `Robot/sketch/sketch.ino` contains the repair: direct
`LSM6DSOXClass(Wire1, address)` instances, 100 kHz bus setup, probes at `0x6A` and
`0x6B`, bridge registration before hardware discovery, a one-second startup
delay, five-second retry, read-failure detection and explicit telemetry. No code
evidence identifies another current device blocking the bus; duplicate address,
wiring, power and pull-up faults remain physical checks.

No WebSocket client or server implementation was found in the active Brain or
Robot Python/HTML sources. Current communication uses HTTP plus MCU Router RPC.

## Live baseline — 2026-07-28

Read-only web inspection reached the Robot at `192.168.68.54:8088`. SSH reached
port 22 but rejected the locally available public keys, so hostname, Linux Python
version, filesystem listing, disk usage, full systemd unit list and kernel I2C
adapter scan could not be collected.

Observed from `/api/status`:

- MCU firmware `10.39`, protocol `bx1.mcu.v1`, Router RPC connected.
- `arduino-router` reported active by Hardware Doctor.
- `drive_outputs_enabled: false`; the configured RS485 drive bus is disabled,
  disarmed and has `protocol_confirmed: false`.
- Microphone `plughw:0,0`, 16 kHz mono; USB Audio Device card 0/device 0.
- IMU identifies as Modulino Movement / LSM6DSOX on `Wire1/Qwiic` at `0x6A`.
- Reported loop period is 20 ms (nominal 50 Hz).
- Five status reads returned identical heartbeat, IMU values and
  `imu_last_update_age_ms` (`21,084,941` ms). The HTTP telemetry sample was stale
  even though `imu_ok` was true. Treat live IMU health as unverified until Router
  RPC is queried directly and freshness is enforced.
- Camera runtime reported `Could not open camera 0`.
- Brain telemetry requests were timing out against configured
  `http://192.168.68.55:8765`; idle-life history also contained an older refused
  connection to `192.168.68.51:8765`.

The deployed firmware does not contain the new read-only `bx1_i2c_scan` RPC, and
production deployment was prohibited. Consequently the only detected address
evidence available in this phase is the firmware-selected IMU address `0x6A`,
not a complete bus scan.

## Phase 1A freshness model

`Robot/python/hardware_bridge.py` performs each Router status RPC and passes the
decoded frame to `HardwareFreshnessTracker` in
`Robot/python/hardware_freshness.py`. A new MCU frame is proven by an advancing
heartbeat, uptime or telemetry sequence; a changing legacy telemetry fingerprint
is used only when counters are absent. Re-reading an identical cached payload
does not refresh the local monotonic timestamp.

IMU freshness prefers `imu_sample_sequence`. For older firmware it combines the
MCU-reported sample age with changes to the legacy sample fields. The effective
age is the more conservative of the MCU-reported age and time since a locally
observed new sample. Missing, negative, non-numeric or infinite ages are unhealthy.

The bridge exposes separate transport, MCU-heartbeat, IMU-presence,
initialisation, sample-freshness and overall-health fields. Compatibility
`mcu_ok` now means connected transport plus fresh MCU heartbeat. Compatibility
`imu_ok` now maps to `imu_healthy`, not merely successful sensor initialisation.
`balance_ready` remains explicitly false.

Freshness thresholds are configured once and used by the tracker:

- `hardware_freshness_warning_ms`: `1500`
- `hardware_freshness_stale_ms`: `3000`

These defaults account for the existing one-second Linux telemetry poll and
modest scheduler/network delay. They remain far below the observed multi-hour
staleness and can be tightened after deterministic MCU polling is separated from
the Brain telemetry interval.

`BX1RobotBodyService.read_body_state()` copies the validated fields into the
sensor packet. Hardware Doctor and the Robot web interface consume those fields
and no longer infer health from Router connectivity alone.
