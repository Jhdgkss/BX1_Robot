# BX1 Onboard Touchscreen Display

Version 10.41 adds a dedicated local display at:

```text
http://127.0.0.1:8088/display
```

The page is designed for a 5-inch HDMI touchscreen mounted in portrait orientation. It displays:

- the robot name and active Brain profile;
- the current runtime state: ready, listening, thinking, speaking, warning or fault;
- the most recently recognised words;
- the latest complete Brain response;
- Brain, STT, microphone, MCU, IMU and camera health;
- pitch, roll, person-presence and Brain latency when available;
- touch buttons for repeat, refresh and the full control interface.

## Unattended startup

Run:

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x INSTALL_BX1_TOUCHSCREEN.sh
./INSTALL_BX1_TOUCHSCREEN.sh
```

The installer creates a desktop autostart entry and can configure the detected display manager for automatic login. It does not remove the user's password or sudo protection.

At the rotation prompt choose:

- **Keep current orientation** when the desktop is already portrait;
- **Right / clockwise** when the panel must be rotated clockwise;
- **Left / anticlockwise** when it must be rotated anticlockwise.

When software rotation is selected, the installer can force an Xorg desktop so `xrandr` and touchscreen coordinate rotation work reliably. This is optional because some installations are already correctly configured.

## Boot sequence

1. Linux boots and starts `bx1-web.service`.
2. The display manager automatically logs in the `arduino` desktop user.
3. The desktop autostart entry runs `tools/bx1_touchscreen_kiosk.sh`.
4. The script disables screen blanking, waits for the body web service and opens the display in kiosk mode.
5. If the browser is closed, the kiosk script restarts it after three seconds.

## Security note

Automatic login gives anyone with physical access to the robot access to its desktop session. Sudo still requires the normal password. Disable automatic login when the robot is used in an unsecured location.
