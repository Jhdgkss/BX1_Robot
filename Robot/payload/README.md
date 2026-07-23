> **Current release: v10.40.** This release uses one permanent ALSA microphone stream, receives the robot name and wake phrases from Robot Brain V2.10.0, and caches Brain-generated acknowledgement/waiting speech locally on the UNO Q.

# BX1 Robot Body Client v10.40

## Install this release

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x APPLY_BX1_V10_40_BRAIN_PROFILE_AUDIO.sh
./APPLY_BX1_V10_40_BRAIN_PROFILE_AUDIO.sh
```

This update does **not** flash or replace the working MCU sketch. It preserves RouterBridge, Modulino Movement, D9/D10/D11 servos, D3 LEDs, quiet-servo mode and disarmed wheel controls.

Install and start Robot Brain V2.10.0 first. In the Brain app, open **Body Wake / Queued Speech**, save the phrase definitions and press **Generate All**. The robot then downloads the generated files automatically or when **Sync Brain profile now** is pressed on its Speech Input page.


This is the matching physical-robot client for Robot Brain v2.7.1. It requests the completed Dot.TTS reply during the normal `/api/chat` or `/api/vision` call, downloads the audio from the Brain API on port 8765, and plays it through the robot speaker with the existing mouth-envelope animation.

## What changed

- One PC connection: Brain API port 8765 handles chat, status and generated reply audio.
- No separate voice-service address is required on the robot.
- Dot.TTS and WSL remain on the Windows Brain PC; the UNO Q does not run the model.
- Existing microphone, speaker, camera, hardware mappings, calibration and API key are preserved by the updater.
- If reply audio cannot be downloaded, the configured lightweight local voice is used as a fallback.
- v10.37 **does require one reviewed MCU sketch update** to restore RouterBridge and move the Modulino Movement to UNO Q Wire1/Qwiic. The sketch remains a minimal I/O shim; high-level behaviour stays in Python.

## Recommended update order

1. Install and start `Robot_Brain_Professional_V2_7_1` on the Windows PC.
2. Confirm the Brain API is online and Dot.TTS reports ready.
3. Copy this entire folder to the robot, for example as `/home/arduino/Arduino_Q_Client_V10_35`.
4. Open an SSH terminal on the robot and run:

```bash
cd /home/arduino/Arduino_Q_Client_V10_35
chmod +x INSTALL_OR_UPDATE_BX1_V10_35.sh
./INSTALL_OR_UPDATE_BX1_V10_35.sh /home/arduino/Arduino_Q_Client_V1
```

The script creates a dated, validated rollback backup under `~/bx1_backups`, stops the body service, copies the new program, migrates `python/config.json`, runs offline checks, and restarts the service. The backup deliberately skips virtual environments, models, runtime audio, diagnostic traces, previous update payloads, logs and archive files; these are not overwritten by the update and are not required for rollback. Fast gzip compression and periodic size messages prevent the installer appearing to hang. If a later step fails, it restores the previous program and configuration.

## Test it

Open `http://BX1-IP:8088`, check the Brain Connection page, and set the Brain address to:

```text
http://WINDOWS-PC-IP:8765
```

Press the connection test, then send a short chat message. The expected sequence is:

1. Brain returns text and generates Dot.TTS audio.
2. BX1 downloads `/api/audio/<filename>` from the same Brain address.
3. The robot speaker plays the reply while its mouth animation follows the WAV envelope.

If the old installation needs to be restored manually, stop `bx1-web.service` and extract the dated `project-before-v10_35.tgz` backup over `/home/arduino/Arduino_Q_Client_V1`.

## Fresh installation

For a robot without an existing client, use the same installer. It copies `python/config.fresh.json` to `python/config.json`. Configure the Brain PC address, microphone, speaker and hardware mapping in the robot web UI afterward.

## v10.36 speech diagnostic changes

The Speech Input test now binds playback to a unique `capture_id`. The body no
longer assumes that `/tmp/bx1_stt_last_*.wav` is the recording just made.
Desktop faster-whisper remains the primary recogniser; local Vosk is deferred
and used only if the Brain STT service is unavailable.

After copying this release over an existing project, run:

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x APPLY_BX1_V10_36_AUDIO_FIX.sh
./APPLY_BX1_V10_36_AUDIO_FIX.sh
```

## v10.42 Brain connection and touchscreen fit

Open **Advanced → Brain Connection** to edit the protocol, Brain IP/hostname and API port independently. The page now preserves text while you type, shows both the Robot Body endpoint and active Brain endpoint, and validates the port before saving.

The onboard `/display` screen shows:

- `Body <robot-ip>:8088`
- `Brain <brain-ip>:<port>`

The display uses fixed viewport bounds, safe edge insets and a Chromium device scale factor of 1 to prevent the right edge being clipped.

## v10.41 onboard touchscreen

Open `http://127.0.0.1:8088/display` for the portrait runtime display. Run `INSTALL_BX1_TOUCHSCREEN.sh` to configure desktop autologin and kiosk startup. See `docs/TOUCHSCREEN_DISPLAY.md`.
