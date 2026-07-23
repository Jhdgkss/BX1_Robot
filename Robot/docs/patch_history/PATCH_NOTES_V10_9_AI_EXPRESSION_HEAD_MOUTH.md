# BX1 Body Client v10.9 - AI Expression Head + Mouth Control

## Purpose

v10.9 makes the head and LEDs part of BX1's behaviour layer instead of just manual hardware tests.

## Added

### Local AI expression engine

When BX1 receives a Brain reply, the UNO Q body client now generates a safe expression plan from the reply text:

- warning/fault language -> amber/red expression
- success/ready language -> green/cyan expression
- questions -> curious head tilt / blue-cyan LEDs
- humour/sarcasm -> purple/cyan with a slight head tilt
- neutral speech -> subtle cyan/blue expression

This works even before the PC Brain App sends formal expression packets.

### Optional Brain `expression` object

The PC Brain App can later return:

```json
{
  "expression": {
    "mood": "curious",
    "mouth_colour": "cyan",
    "eye_colour": "blue",
    "yaw": -3,
    "pitch": 3,
    "roll": 2,
    "nods": 0,
    "duration_s": 4
  }
}
```

The body client clamps it and converts it to safe `set_head_pose` and LED commands.

### Natural head motion

- idle micro-look behaviour
- speaking pose
- optional nods
- return-to-home after reply

The hardware limits still come from the Hardware Registry.

## Important

This will only move the head if:

1. The servo pins are enabled in Hardware / GPIO.
2. Hardware Registry has been applied to MCU.
3. The MCU sketch currently running provides the v10.5+ compact RPC methods.
4. The servos have separate power and common ground.

The mouth LED will only pulse with speech if robot TTS is enabled or the Brain reply is processed through the body client.
