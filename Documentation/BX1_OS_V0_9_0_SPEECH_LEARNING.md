# BX1 OS v0.9.0 — Speech Learning and Dual UI Modes

The management interface has two presentations backed by the same APIs and themes:

- Desktop mode (`?ui=desktop`) keeps the permanent sidebar and 45/55 voice workspace.
- Touchscreen mode (`?ui=touchscreen`) presents Audio Status, Speech Recognition, Conversation, Diagnostics, Quick Controls and System Summary as a linear touch layout. The selected mode is retained in browser storage.

## Speech learning

Speech Learning reviews Body recognition metadata before dataset inclusion. Raw Whisper text is retained separately from corrected text and the extracted request. Reviewers may approve, ignore, add vocabulary terms or create correction rules. Nothing is uploaded or fine-tuned automatically.

Vocabulary and correction data are stored in the management runtime JSON store and exposed at `/api/speech-learning`. Imports must contain bounded JSON arrays of objects; dataset export remains an explicit operator action.

## Brain hotword synchronisation

BX1 OS sends enabled vocabulary terms, variants, categories, speaker scope and a monotonically increasing revision to the Brain `/api/stt/vocabulary` contract. The Brain reports acceptance, active count, revision, model and rejected terms. Faster-Whisper receives the active terms through its supported `hotwords` argument. Disabled terms are omitted and unchanged revisions are not resent.

The transcription order is: raw Faster-Whisper text → vocabulary-biased result → safe, case-insensitive phrase corrections → wake/request extraction. Raw text and applied correction IDs remain in diagnostics. Vocabulary biasing improves decoder context; it is not model training or fine-tuning.

If the Brain is disconnected, management retains the pending revision and retries on the next update. Check `/api/stt/vocabulary/status` and the Speech Learning sync indicator. A successful vocabulary update does not imply that the model has been retrained.

## Privacy and retention

Audio capture remains Robot Body-owned. Hard microphone mute prevents capture. Diagnostic retention is configured by the Body; approved examples require manual review. When Brain or Body telemetry is unavailable, the UI reports that state instead of inventing recognition data.

## Troubleshooting

Check `/api/audio/bridge` for RMS, threshold and gate state, `/api/audio/speech-scan` for structured transcript ranges, and `/api/speech-learning` for review data. A disconnected Brain is shown as disconnected; it does not block local diagnostics.
