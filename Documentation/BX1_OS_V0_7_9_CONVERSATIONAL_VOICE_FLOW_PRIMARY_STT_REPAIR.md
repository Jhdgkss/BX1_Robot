# BX1 OS v0.7.9 Conversational Voice Flow and Primary STT Repair

v0.7.9 makes the Body-owned wake conversation window responsive: the default
is 15 seconds, wake acknowledgement uses the existing Body playback lifecycle,
and only state transitions are recorded in the temporary Live Voice console.
Countdowns and echo-tail updates remain visible as live status, but do not
produce repeated transcript entries. Empty or rejected speech is never sent to
Brain.

Primary recognition remains Brain Faster-Whisper. The Body sends only a
validated 16 kHz mono WAV request to `POST /api/stt/transcribe`, with a bounded
12-second request timeout. Brain now returns structured recognition failures
as an HTTP 200 response, so the Body can show the actual failure reason rather
than misclassifying it as a transport error and silently falling back to Vosk.
Local Vosk is retained as a clearly labelled fallback for a genuine unavailable
or failed primary service. No raw audio is retained, logged, exported, or put
in the shared transcript.

The Speech Test reports metadata only: live level, measured noise floor, gate,
recognised text, engine, elapsed time and bounded fallback/failure reason. Its
calibration suggestion is advisory and applies only after the operator chooses
the existing settings Apply action. Gate changes cannot remove physical fan,
servo, or microphone noise.

## Windows Brain update

The Brain is not included in the LEO OS archive and has no configuration or
model migration. Preserve the existing `Brain` configuration, `.venv`, runtime
state and models. If applying the v0.7.9 Brain patch, replace only
`Brain/main_pyqt.py`, close the running Brain application, launch it once with
the existing `Brain\\START_BX1_BRAIN.bat` launcher, and verify its existing
`http://127.0.0.1:8765/api/status` endpoint. Do not copy any configuration,
models, or other Brain files from the patch.

## LEO deployment scope

The OS archive carries the BX1 OS UI, server, service and release metadata. A
separate Body patch carries only `Robot/python/main.py`; the deployment script
backs it up and replaces it atomically before one `bx1-web.service` restart.
The script does not execute Brain changes and does not modify camera, MCU,
motors, servos, firmware, or Brain configuration.
