# Current System Map

This map describes the active source tree, not a proposed replacement.

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
| Configuration | Robot `Robot/python/config.json`, profile `robot_profile.json`, defaults/examples, and startup options in `Robot/python/main.py`; Brain `Brain/config/app_config_*.json`, personality and robot-profile JSON files. |
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
