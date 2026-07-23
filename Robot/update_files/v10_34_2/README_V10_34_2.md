# BX1 Body v10.34.2 — Fast Wake, Post-Speech Follow-up and Response Feedback

This hotfix is based on the voice trace recorded on 19 July 2026.

## Trace findings

- `plughw:0,0` is the correct microphone and its recorded level is healthy.
- A spoken wake acknowledgement occupied the microphone immediately after `Hey`, so the following question could be missed.
- The follow-up timer started when LLM text arrived, then continued counting down through 16–19 seconds of Chatterbox generation and roughly 12 seconds of playback.
- Local thinking cues were disabled in the saved configuration.
- OpenCV repeatedly tried and failed through GStreamer, producing continuous camera warnings and unnecessary load.

## Changes

- Keeps `Hello`, `Hey` and `Robot` wake words.
- Uses a fast chirp/LED wake acknowledgement and immediately reopens the microphone.
- Starts a 90-second follow-up window after physical speech playback ends.
- Enables the accepted-command chirp and cached thinking phrases.
- Preserves `plughw:0,0` permanently.
- Slightly improves short-phrase endpointing without weakening the noise gate.
- Uses V4L2 directly for the USB camera before generic OpenCV/GStreamer fallback.
- Includes the v10.34.1 web control protection so microphone selections do not snap back during refresh.
- Restores bounded idle-life micro-actions and self-chatter.

No MCU firmware is flashed.
