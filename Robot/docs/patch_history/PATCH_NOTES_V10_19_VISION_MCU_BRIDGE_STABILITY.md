# BX1 Body Client v10.19 - Vision Cue + MCU Bridge Stability

This patch is intentionally code-only. It does **not** overwrite `python/config.json`.

## Fixes

- Expands automatic camera/vision trigger detection for natural spoken prompts such as:
  - "what am I holding?"
  - "what is in my hand?"
  - "what am I showing you?"
  - "look at my hand"
- Improves Vosk/punctuation tolerance for vision routing.
- Updates UI/server version labels to v10.19.
- Adds clearer MCU bridge error messages when arduino-router is alive but the MCU sketch has not registered the BX1 methods.
- Avoids hiding the real RouterBridge problem behind serial fallback errors on UNO Q.

## New scripts

- `tools/BX1_RUNTIME_SETTINGS_FIX.sh`
  - Preserves existing config.
  - Forces web UI enabled.
  - Sets normal speech sample time to 10 seconds if it was too short.
  - Adds extra camera trigger phrases.
  - Restarts the web service.

- `tools/BX1_MCU_BRIDGE_PERMANENT_REPAIR.sh`
  - Stops the body service.
  - Compiles the current MCU sketch.
  - Uploads it to the UNO Q target.
  - Restarts arduino-router.
  - Runs the Router RPC bridge check.
  - Restarts the body service.

## Important

If Hardware / GPIO says methods such as `bx1_config_led_bus` or `bx1_set_command` are not available, the Linux side is running but the MCU sketch is missing/out-of-date. Run:

```bash
cd ~/Arduino_Q_Client_V1
chmod +x tools/*.sh
./tools/BX1_MCU_BRIDGE_PERMANENT_REPAIR.sh
```

If the upload target is not the board's own IP, pass it explicitly:

```bash
./tools/BX1_MCU_BRIDGE_PERMANENT_REPAIR.sh <UNO_Q_IP_OR_UPLOAD_PORT>
```
