# BX1 Body Client v10.11 - Brain/body split, STT repair and persistent settings

This patch formalises the split between the Arduino UNO Q body and the desktop Robot Brain.

## Ownership model

- **UNO Q body client owns:** hardware mapping, microphone capture, camera capture, speaker playback, wake words, telemetry, lights, servos, safety validation and command acknowledgement.
- **Desktop Robot Brain owns:** LLM, web/news/weather tools, memory, personality overlay, voice generation, action planning and multi-robot brain identity.
- Every robot-to-brain request carries `robot_id`, `body_state`, `robot_profile`, capabilities and version data, so multiple robots and multiple Brain apps can coexist without hard-coded BX1 assumptions.

## Fixes

- Adds `vosk` to the base body requirements so the wake/STT page no longer reports `No module named 'vosk'` after a normal UNO Q install.
- Adds clearer STT diagnostic hints showing the exact Python executable and repair command.
- Settings now save to both `python/config.json` and `runtime/config/body_config.local.json`.
- Robot profile now saves to both `python/robot_profile.json` and `runtime/config/robot_profile.local.json`.
- The runtime overlay is loaded on startup, so settings survive service restarts and normal code-only patch updates.
- Version bumped to **BX1 Body Client v10.11**.

## After applying

Run this once on the UNO Q if STT is still red:

```bash
cd ~/Arduino_Q_Client_V1
chmod +x INSTALL_VOSK_STT.sh
./INSTALL_VOSK_STT.sh
sudo systemctl restart bx1-web.service
```

Then open `http://BX1.local:8088/microphone` and press the STT check/test buttons.
