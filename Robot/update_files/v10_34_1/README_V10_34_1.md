# BX1 Body v10.34.1 — microphone selection persistence

This hotfix stops the 1.25-second status refresh from rebuilding the Speech Input controls while the user is editing them. It also verifies the selected microphone after saving and sets the required capture device to `plughw:0,0` during installation.

It does not flash the MCU and does not change Brain/TTS settings.
