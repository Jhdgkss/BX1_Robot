# BX1 OS v0.7.7 — Body Speaker Echo Suppression

Robot Body remains the sole microphone and speaker owner. v0.7.7 uses the existing `TextToSpeech` playback lifecycle: `speech_audio_file_start` occurs immediately before the player starts and `speech_audio_file_stop` occurs in the player path's `finally` block. Those events set and clear the Body's authoritative `speaker_playback_active` state.

ALSA capture and its metadata heartbeat continue throughout playback. While actual playback is active, and during the configurable post-playback tail, completed microphone captures are discarded before STT queueing. Existing queued work is checked again before desktop STT and before Brain submission. No recognised text from suppressed audio enters the shared BX1 OS conversation feed.

`speaker_echo_tail_ms` is the only new allowlisted v1 voice setting. It defaults to 1500 ms and is bounded to 250–5000 ms. The existing versioned Body settings API atomically preserves unrelated `config.json` values, ownership and mode.

BX1 OS shows the Body-provided state detail, last accepted request, and separate discarded/noisy metadata. The shared temporary RAM transcript receives accepted user speech only, Leo replies only, and bounded system/fault states.
