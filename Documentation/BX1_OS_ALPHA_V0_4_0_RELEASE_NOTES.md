# BX1 OS Alpha v0.4.0 Release Notes

## Summary

BX1 OS Alpha v0.4.0 introduces failure-isolated, read-only hardware discovery
and a dedicated Audio page. Hardware and audio values flow through BX1 Core;
the Management Interface never interrogates devices directly.

## Added

- central hardware inventory and adapter contract;
- metadata-only audio, camera, serial, input, display, network and battery
  discovery;
- Robot Body loopback adapter with an allowlisted GET surface, short timeouts,
  response limits and sanitised projections;
- proxied MCU, IMU, microphone, speaker, STT, TTS, camera and fault status;
- observation envelopes with timestamp, source, quality, stale and error data;
- observer-only hardware diagnostics;
- six read-only hardware, audio and Robot Body APIs;
- dynamic Hardware and Diagnostics pages and a dedicated Audio page; and
- deterministic offline hardware, API, UI and safety tests.

## Safety

- no hardware device is opened;
- no microphone or camera stream is started;
- no serial, I2C, SPI, RS485, GPIO, PWM or actuator operation is issued;
- no ALSA mixer or playback operation is issued;
- all management write methods remain disabled;
- optional hardware absence is not a global OS fault;
- `bx1-web.service`, port 8088 and the Robot Body UI are unchanged; and
- no robot was accessed or deployed to while producing this release.

## Release identity

- Version: `0.4.0`
- Tag: `BX1_OS_ALPHA_v0.4.0`
- Default mode: install-only
- Install root: `/home/arduino/BX1_OS`
- Service: `bx1-os-alpha.service`
- Management port: `8089`

## Known limitations

This release observes only. Camera streaming, audio capture/playback, level
generation, mixer changes, device probing, configuration editing, service
control and hardware control remain intentionally unavailable.
