# BX1 Body Client v10.10 - Startup Repair + Robot Brain Voice Bridge Sync

This update aligns the Arduino Q body client with the current PC Robot Brain V1.1.x voice workflow and fixes the common startup failure where the web app does not start on boot.

## Fixed startup / crash visibility

- Added `REPAIR_BX1_STARTUP.sh` to reinstall and restart the `bx1-web.service` startup service.
- Added `tools/install_bx1_web_service.sh` to write the correct systemd service using the actual project folder.
- Replaced the old service path that still pointed at `BX1_UNO_Q_Robot_Body_v0_1`.
- Updated `tools/run_robot_body.sh` so systemd uses the project `.venv` Python when available.
- Updated `START_BX1_WEB.sh` so immediate crashes are visible and logged to `runtime/logs/web_startup.log`.
- Added `DIAGNOSE_BX1_WEB.sh` to collect service status, port status, curl test and recent logs.

## Robot Brain / Chatterbox TTS bridge update

- UNO Q now defaults to the PC Robot Brain robot endpoint:
  - speak: `/robot/speak`
  - status: `/robot/tts/status`
- Added support for `relative_audio_url` returned by the Robot Brain TTS service.
- Keeps compatibility with older `/speak` endpoint only as a fallback if `/robot/speak` returns 404.
- Added **Check Robot Brain TTS** button to the Speech / Voice page.
- Added endpoint fields to the Speech / Voice page for diagnostics and future compatibility.

## Version

- Body Client version updated to `v10.10`.

## After copying onto BX1

Run:

```bash
cd ~/Arduino_Q_Client_V1
chmod +x REPAIR_BX1_STARTUP.sh START_BX1_WEB.sh STOP_BX1_WEB.sh DIAGNOSE_BX1_WEB.sh
./REPAIR_BX1_STARTUP.sh
```

Then check:

```bash
curl -I http://127.0.0.1:8088
```

From another device open:

```text
http://BX1.local:8088
```
