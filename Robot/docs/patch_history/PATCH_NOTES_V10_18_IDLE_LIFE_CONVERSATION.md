# BX1 UNO Q Body Client Patch v10.18 - Idle Life + Conversation Polish

Date: 2026-07-08

## Added

- New **Idle Life / Bored Routine** page in the web UI.
- Autonomous idle-life runtime that can:
  - perform small head/LED micro-actions after a configurable idle delay,
  - speak occasional bored/self-chatter phrases,
  - optionally ask the Brain App for a short internet-curiosity fact/comment,
  - enter a quiet sleep state after a longer inactivity timeout.
- Idle-life settings are saved in `python/config.json`.
- Idle-life runtime is visible in `/api/status` and in the top status pills.
- Idle chatter phrases are included in the local Chatterbox cue cache as `idle_chatter_01`, `idle_chatter_02`, etc.

## Changed

- Wake/session state now exposes conversation-active timing to the idle routine, so idle chatter does not interrupt an active spoken conversation.
- User speech and manual text input reset the idle-life timer.
- Startup compatibility wrapper and safer systemd restart behaviour from v10.17A are included again to prevent regression.

## Defaults

- Idle life: enabled.
- Micro head/LED actions: enabled after 120 seconds.
- Self chatter: enabled after 300 seconds.
- Max idle comments: 3 per hour.
- Internet curiosity: disabled by default; enable it from **Idle Life** when the Brain App web route is working.
- Sleep: after 1800 seconds; silent by default.

## Apply

Copy this overwrite patch into `/home/arduino/Arduino_Q_Client_V1`, overwrite existing files, then run:

```bash
cd ~/Arduino_Q_Client_V1
chmod +x main.py START_BX1_WEB.sh STOP_BX1_WEB.sh REPAIR_BX1_STARTUP.sh DIAGNOSE_BX1_WEB.sh tools/*.sh
./REPAIR_BX1_STARTUP.sh
```

Then open:

```text
http://BX1.local:8088/idle
```
