# Patch notes v9.4 - Robot Brain Voice + Hardware Map

This update makes the UNO Q robot body client a better companion to Robot Brain V1.

## Voice

New TTS backend:

- `brain-tts`

When selected, the UNO Q does not generate the robot voice locally. Instead it sends the text to the PC Brain App TTS service, normally:

```text
http://YOUR_PC_IP:8091/speak
```

The PC generates the Chatterbox voice, the UNO Q downloads the WAV/MP3, and the robot plays it through its own speaker. This is how the robot speaks with the same voice as the Brain App without running heavy Chatterbox models on the UNO Q.

Recommended setting on the web page:

```text
Speech / Voice > Backend: Brain App Chatterbox voice
Brain App TTS URL: http://YOUR_PC_IP:8091
Brain voice key: chatterbox_bx1
```

## Hardware / GPIO page

New web page:

```text
Hardware / GPIO
```

It lets you assign:

- head rotation/yaw servo
- head up/down/pitch servo
- head tilt/roll servo
- eyes NeoPixel LED strip/ring
- mouth NeoPixel LED strip/ring

The map is saved in:

```text
python/config.json
```

After changing pins, press:

```text
Apply Hardware Map to MCU
```

The page also has small bench-test buttons for head yaw/pitch/roll and LED colours.

## MCU sketch

The sketch now supports:

- 3 head servos: yaw, pitch, roll
- runtime hardware configuration packets
- target LEDs: eyes, mouth, or all
- `set_head_pose` with `yaw_deg`, `pitch_deg`, and `roll_deg`
- `set_led`, `set_eye_led`, or `set_device_led`

## Notes

NeoPixel support requires the Adafruit NeoPixel library in the Arduino/MCU environment.

Start with all hardware outputs disabled and only enable one device at a time while bench testing.
