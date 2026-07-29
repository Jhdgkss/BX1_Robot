# BX1 OS v0.7.4 Live Voice Monitor

Robot Body continues to own the microphone, wake/STT and speaker. Its active
ALSA capture loop emits only bounded per-frame level metadata to the Body
runtime: RMS/peak dBFS, estimated noise floor, threshold, gate and timestamp.
No waveform, raw audio, recording, camera or hardware control crosses the
boundary.

`GET /api/bx1-os/audio-bridge` returns that fresh observation together with the
current voice state and the latest recognised text, STT engine, confidence and
bounded rejection/failure reason. If the Body has no fresh active-capture sample,
the response marks the measurement unavailable and gives an explicit reason;
the OS must not substitute a placeholder level.

BX1 OS presents this data in a compact dashboard card and the Audio Voice Monitor.
Recognised words and manual/reply/failure items remain only in browser memory for
the current tab. They are not written to OS logs, diagnostics, events, exports or
server storage.
