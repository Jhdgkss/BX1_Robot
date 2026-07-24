ROBOT BRAIN V2.12.0 — RUNTIME WORKFLOW AND STUDIOS

1. Close Robot Brain.
2. Dot.TTS may remain running; this patch does not change the voice service.
3. Extract this patch ZIP fully.
4. Run APPLY_BX1_BRAIN_V2_12_0.bat.
5. Enter the folder containing the working main_pyqt.py.
6. Start Robot Brain normally.

The installer creates a timestamped backup and restores it automatically if
compilation or validation fails.

WHAT CHANGES
- Main navigation becomes Home, Runtime, Knowledge, Skills, Body, System,
  Studios and Help.
- Personality Studio owns identity, traits, prompt, theme and voice binding.
- Voice Lab owns reference voice creation and benchmarking.
- Main Runtime keeps only active identity display and operational controls.
- Memory moves to Knowledge.
- Shared Dot.TTS startup options move to System.

WHAT IS NOT CHANGED
- Leo and BX1 robot profiles
- saved personality files
- trained/reference voice files
- memory or documents
- body/hardware configuration
- API ports and runtime data
