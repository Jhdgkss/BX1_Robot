# BX1 UNO Q Body Client v10.28

This update is based directly on `Arduino_Q_Client_V1(6).zip`.

## What it fixes

- Applies the v10.27 live-preview, OpenCV-state, idle-life and STT changes to the actual saved configuration, which was still marked v10.26 in the supplied snapshot.
- Installs the larger Vosk English model by default to improve complete-sentence recognition.
- Keeps 700 ms pre-roll, 1350 ms natural end silence and gentler audio noise reduction.
- Treats “hi” as a natural alias for the configured “hello” wake word without changing the visible defaults: Hello, Hey, Robot.
- Sends autonomous phases to the desktop Brain as `Input [IDLE]` with concise provenance, while the Brain still writes the response in BX1’s personality.
- Retains automatic cached camera preview updates only while the Vision page is open.
- Preserves the Brain PC address, microphone device, D9/D10/D11 servo mapping, trims and LED ranges.

## Install

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x APPLY_BX1_V10_28.sh
./APPLY_BX1_V10_28.sh --project=/home/arduino/Arduino_Q_Client_V1
```

The installer attempts OpenCV and the improved Vosk model. Use `--skip-opencv` or `--skip-better-stt` only when necessary. It does not flash MCU firmware.
