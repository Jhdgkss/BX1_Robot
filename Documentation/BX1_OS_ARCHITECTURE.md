# BX1 OS Architecture

## Safety boundary

> The Brain chooses the goal. The Robot performs it safely.

High-level intent crosses the Brain/Robot boundary. Raw, unchecked actuator control
does not. Robot-side validation, limits, timeouts, state and telemetry remain
authoritative even when the Brain requests an action.

## Brain responsibilities

- Conversation and personality.
- Vision, object recognition and person recognition.
- World model and memory.
- Navigation planning, skill selection and high-level commands.
- Internet and document retrieval.

## Robot responsibilities

- IMU sampling, balance control and wheel control.
- RS485 communication and encoder feedback.
- Head control, distance sensing and LEDs.
- Safety, command validation and command timeout.
- Telemetry and diagnostics.

## Current phase boundary

This phase establishes the baseline and adds read-only diagnostics. Wheel drive,
balancing, RS485 motor commands and automatic firmware deployment remain disabled.
Existing voice, wake, STT, TTS, camera, touchscreen, web, servo and LED behaviour
is preserved.

## Runtime model

The desktop Windows Brain is a PyQt application with an embedded HTTP API and
background workers. The UNO Q Linux processor runs the Robot Python body service,
web server, voice/camera clients and Router RPC client. The UNO Q STM32 MCU runs
the Arduino sketch for deterministic I/O, head servos, addressable LEDs and
Modulino Movement sampling.

The present protocol has three layers:

1. Robot-to-Brain HTTP (`Robot/python/bx1_robot_client.py`).
2. Robot web HTTP (`Robot/python/web_control.py`).
3. Linux-to-MCU MessagePack Router RPC, with serial fallback
   (`Robot/python/hardware_bridge.py`, `Robot/sketch/sketch.ino`).

This is a baseline, not yet the final shared versioned Brain/Robot safety protocol.
