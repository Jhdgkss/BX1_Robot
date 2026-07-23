# BX1 Body Client v10.14 - Brain TTS Auto-Sync + Hardware UI Fix

This patch addresses the two issues seen after v10.13:

1. **Brain App TTS URL no longer needs to be entered separately.**
   - The robot now derives the Brain TTS URL from the saved Brain App URL.
   - Example: Brain API `http://192.168.68.53:8765` automatically gives Brain TTS `http://192.168.68.53:8091`.
   - Placeholder values such as `http://YOUR_PC_IP:8091` are ignored and replaced by the derived address.

2. **Hardware/telemetry pages no longer fail with `hardwareFormDirty is not defined`.**
   - This was a browser-side JavaScript variable issue, not proof of a hardware fault.
   - The variable is now initialised before refresh handlers run.

The local Chatterbox cue cache still depends on the Windows Brain TTS service being reachable on port 8091 from the UNO Q. If the desktop Brain can generate Chatterbox locally but the UNO Q reports `No route to host`, check Windows Firewall inbound access for Python on port 8091.
