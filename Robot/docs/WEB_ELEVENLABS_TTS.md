# Legacy Body Voice Configuration

Direct cloud/ElevenLabs voice selection on the UNO Q body client is obsolete in v10.24.

Leo’s active TTS engine and voice are selected in the desktop Brain App. The UNO Q body client receives/downloads the generated speech and plays it through the robot speaker. This prevents the body and Brain from maintaining different voice selections.

The old compatibility fields remain in configuration only so an earlier service can fail safely. They are not exposed by the current body diagnostic console and cannot override the normal Brain-owned voice route.
