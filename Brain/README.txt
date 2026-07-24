BX1 DOT.TTS FORCE STANDARD MODE V3 FIXED

Purpose
-------
Disables optional torch.compile optimisation so Dot.TTS does not require nvcc.
This version fixes the V2 installer PowerShell pipe/caret parsing fault.

Install
-------
1. Stop the current Dot.TTS voice service.
2. Run APPLY_BX1_DOT_TTS_FORCE_STANDARD_V3_FIXED.bat
3. Select the Robot Brain project folder.
4. Start START_DOT_TTS_MF.bat.
5. Confirm the console says:
   Mode: standard compatibility mode (torch.compile disabled)
6. In Voice Lab press Refresh health and verify "optimize": false.

The installer creates a timestamped backup and restores it if validation fails.
