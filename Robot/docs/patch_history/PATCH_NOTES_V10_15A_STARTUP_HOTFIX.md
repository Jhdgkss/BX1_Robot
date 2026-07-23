# BX1 UNO Q Body Client v10.15A Startup Hotfix

Fixes a startup crash introduced in v10.15 where the body client tried to derive the Brain TTS URL before the Brain App URL had been configured.

Changes:
- Brain TTS URL derivation no longer raises during startup.
- If Brain TTS is selected but no Brain URL is configured, startup uses local espeak-ng fallback until the Brain Connection page saves the PC URL.
- The web service can now start with a blank/new config.
- The "same host voice" sync returns a clear error instead of crashing if the Brain URL is blank.

Apply by extracting over `/home/arduino/Arduino_Q_Client_V1` and restarting the service.
