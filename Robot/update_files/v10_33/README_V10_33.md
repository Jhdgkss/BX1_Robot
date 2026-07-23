# BX1 UNO Q Body Client v10.33

## Natural conversation and voice safety

This patch keeps the existing natural wake words **Hello**, **Hey** and **Robot**, while preventing room noise and recogniser repetition from becoming commands.

### Main changes

- Removes the prose wake instruction that could leak into faster-whisper transcripts.
- Rejects repeated words, repeated phrases, impossible word rates and known STT prompt leakage before contacting the Brain.
- Keeps generic one-word wake choices, but only accepts them near the start of a sleeping utterance.
- Removes the unsafe `rowboat` alias for `robot`.
- Raises the speech-start gate from the unusually permissive v10.32 values.
- Uses one clear voice phase at a time: listening, processing, building voice, speaking and ready.
- Keeps the microphone muted while the reply is being generated or played, including the post-playback guard.
- Refreshes the robot web state roughly every 1.25 seconds instead of every 5 seconds.
- Keeps the conversation open for 90 seconds after a successful reply, so normal follow-up speech does not require another wake word.
- Adds varied cached wake acknowledgements: `Yes John?`, `I'm listening.` and `Go ahead.`
- Uses a quick local chirp and at most one short spoken thinking cue for slow replies.

## Installation

Copy this patch into `/home/arduino/Arduino_Q_Client_V1`, then run:

```bash
cd /home/arduino/Arduino_Q_Client_V1
chmod +x APPLY_BX1_V10_33.sh
./APPLY_BX1_V10_33.sh
```

The installer backs up the current Python files and config, migrates the existing config without replacing the selected microphone, Brain address, hardware setup or wake-word list, validates the patch and restarts `bx1-web.service`.

## First checks

1. Open the body web page and confirm version 10.33.
2. Leave the robot in a quiet room for at least ten minutes. No command should be emitted.
3. Say `Hello`, `Hey` or `Robot`; BX1 should acknowledge and listen for the next phrase.
4. Ask a normal question and watch the page change through processing/building voice/speaking before returning to ready.
5. Check `/tmp/bx1_stt_last_submitted.wav` if a phrase is rejected unexpectedly.

This patch has static and automated transcript-guard tests, but microphone thresholds still need a physical on-robot test because acoustic conditions vary by speaker, microphone and room.
