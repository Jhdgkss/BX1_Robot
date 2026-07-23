# BX1 Body Client v10.30 — Heard Text and Thinking Phases

This update keeps the listening and thinking chirps, then adds short spoken progress phases when the Brain is still working:

1. thinking LED and chirp after about 0.35 seconds;
2. a short phrase such as “Let me check that” after about 1.15 seconds;
3. one further phrase after about 5.5 seconds for slow web, weather or vision requests.

The Conversation page now shows:

- the raw speech transcription;
- the accepted command after wake-word removal;
- the wake word and confidence when available;
- the active thinking phase and phrase.

The desktop Brain still owns the final reply, personality and autonomous idle dialogue. The body only renders short bounded progress feedback while waiting.
