# BX1 Body Client v10.29

This update adds immediate progress feedback while the desktop Brain is generating a reply.

- A distinct three-note thinking chirp starts about 0.45 seconds after a request.
- The thinking LED state is applied while the request is pending.
- A second quiet chirp can occur after four seconds if the model is still working.
- The desktop Brain continues to own personality and spoken filler wording, preventing duplicate speech.
- Includes all v10.28 voice, idle-provenance and live-vision changes.
- Preserves the Brain address, microphone, Vosk model, servo trims, GPIOs and LED ranges.
