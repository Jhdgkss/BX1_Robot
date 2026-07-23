# BX1 Body Client v10.12 - conversation mode, instant wake cues and hardware load

## Added
- Wake-word acknowledgement now triggers immediate body-owned cues before the Brain reply path is involved.
- Conversation follow-up mode keeps BX1 awake after a reply, so the next sentence does not need the wake word.
- Sleep phrases such as `sleep`, `go to sleep`, `stand down` and `stop listening` close the conversation and return to wake-word-only mode.
- Fast local acknowledgement speech uses espeak-ng directly, bypassing slow Brain/Chatterbox generation for short phrases like `Yes John?` and `I am checking that.`
- Performance page now shows graphical UNO Q CPU, memory, temperature, process/thread/RSS and latency trend metrics.
- Body telemetry now includes `system_load` so the laptop Brain can see robot-side load.

## Notes
The full-quality reply still uses the selected Robot Brain/Chatterbox voice. The fast acknowledgement path is intentionally short and local so the robot appears alive immediately.
