# BX1 Body v10.34 — Immediate Feedback and Restored Idle-Life

This update is based on BX1 body v10.33.1 and the voice trace captured on 19 July 2026.

## What the trace proved

For the crumpet question, the Brain returned its text in about 1.7 seconds, but the Chatterbox audio did not become physically ready for roughly another 29 seconds. For the BBC request, the Brain text took about 6.4 seconds and Chatterbox generation/download added roughly another 48 seconds.

The trace also showed that all local progress speech was disabled in configuration:

- `thinking_cues_enabled: false`
- `thinking_cue_speak: false`
- `voice_command_immediate_cue_enabled: false`
- `brain_controls_thinking_cues: true`

Cached Chatterbox cue WAV files were already present on the robot, but the ownership logic prevented them from being used.

## Corrections

- Gives an immediate audible and visible acknowledgement after a valid command.
- Plays a cached Chatterbox progress phrase after about 1.1 seconds.
- Repeats a different short progress phrase about every 8 seconds during genuinely slow Chatterbox generation.
- Keeps progress cues alive until the final reply audio is physically ready to play, not merely until the LLM text returns.
- Prevents a progress phrase and the main reply from talking over each other.
- Keeps the web state as `PROCESSING` or `SPEECHGEN` for progress cues; it only shows `SPEAKING` when the final answer reaches the speaker.
- Restores bounded idle-life micro-actions and short self-chatter.
- Keeps `Hello`, `Hey`, and `Robot` as wake words.
- Preserves the configured microphone device, including `plughw:0,0`.
- Enables shorter TTS chunks so longer replies begin speaking sooner.
- Adds journal timing lines for Brain TTS generation, download, playback start and playback completion.

## Default feedback sequence

1. Valid speech: immediate confirmation chirp and heard LED state.
2. About 0.18 seconds: thinking chirp.
3. About 1.1 seconds: `Let me think.`
4. Every 8 seconds if still waiting: `One moment.`, `I am checking that.`, `Hmm.`, then `Processing.`
5. When final audio is ready: progress cues stop and the answer begins.

The phrases use cached Chatterbox WAV files when available. They do not require the large voice model to generate them live.

## Installation

Copy this package into:

```text
/home/arduino/Arduino_Q_Client_V1
```

Then run:

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x APPLY_BX1_V10_34.sh
./APPLY_BX1_V10_34.sh
```

The installer backs up the current files, migrates the existing configuration, performs syntax/self-tests, restarts the service and verifies the web page on port 8088. It does not flash the MCU.

## After installation

Open **Wake and microphone settings** and verify the capture device remains:

```text
plughw:0,0
```

The existing cached local voice cues should be reused. Regenerate them only if you want different wording or a different selected Chatterbox voice.
