# BX1 Body Client v10.13 - Echo Guard + Local Chatterbox Cues

This update targets the issue where the USB webcam microphone can hear BX1's own speaker and feed the robot reply back into Vosk STT.

## Added

- STT echo guard: the wake listener pauses while TTS is queued, generating, playing, or in a short post-speech guard period.
- Follow-up conversation window: after a reply, BX1 stays awake for a configurable period so the next sentence does not need the wake word.
- Sleep commands: `sleep`, `go to sleep`, `stand down`, `stop listening`, `that is all`, `goodnight`.
- Local Chatterbox voice cue cache: wake, thinking, and sleep phrases can be pre-rendered by the Brain PC and stored on the robot body as WAV files.
- Thinking Cues page controls for cue cache, wake acknowledgement, STT mute while speaking, and conversation window timing.
- Hardware load telemetry using Linux `/proc`: CPU estimate, memory, process RSS, threads, disk, temperature where available.
- More graphical performance page cards for body hardware load.

## Behaviour change

- Thinking cues prefer cached local Chatterbox WAV files. They no longer use live Brain TTS by default because that increases latency.
- If the cue cache is missing, BX1 can use a very short espeak emergency acknowledgement so wake feedback is immediate. Regenerate the local cue cache to get the Chatterbox voice.

## Recommended first use

1. Start the Robot Brain desktop app and TTS service.
2. On the robot web page, go to Brain Connection and press `Use This Browser PC for Brain + Voice`.
3. Go to Thinking Cues.
4. Press `Regenerate Local Chatterbox Cues`.
5. Test wake word, follow-up speech, and `sleep`.
