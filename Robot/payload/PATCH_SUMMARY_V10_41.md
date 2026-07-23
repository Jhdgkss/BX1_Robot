# BX1 Robot Body v10.41 — Onboard Touchscreen

This Linux-side update adds a portrait touchscreen runtime display and unattended desktop startup support. It does not modify or flash the MCU sketch.

## New features

- `/display`, `/screen` and `/touchscreen` routes for the onboard display.
- Compact `/api/touchscreen` runtime endpoint.
- Live robot name and active Brain profile.
- Current listening, thinking, speaking and safety state.
- Latest recognised speech and complete robot response.
- Brain, STT, microphone, MCU, IMU and camera status.
- Pitch, roll, person-presence and Brain latency indicators.
- Touch controls for repeat, refresh and full controls.
- Automatic desktop login configuration for GDM, LightDM, SDDM and LXDM.
- Kiosk browser autostart with screen-blanking disabled.
- Optional screen and touch-coordinate rotation under Xorg.

## Installation

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x APPLY_BX1_V10_41_TOUCHSCREEN.sh
./APPLY_BX1_V10_41_TOUCHSCREEN.sh
```

Then configure unattended display startup:

```bash
./INSTALL_BX1_TOUCHSCREEN.sh
```
