# BX1 v10.35 Control Ownership

The UNO Q body client and the desktop Brain App must not independently control the same high-level behaviour. BX1 v10.35 makes the boundary explicit in both configuration and code.

## Desktop Brain App owns

| Function | Reason |
|---|---|
| Robot identity, name and personality | One authoritative character and prompt stack |
| LLM/model selection and generation settings | Prevents the body from maintaining a second model configuration |
| Memory and internet-use policy | Keeps retrieval and privacy decisions in the Brain |
| TTS engine, voice model and emotional delivery | The Brain selects Dot.TTS/voice settings; the body only plays the returned audio |
| Spoken thinking-cue wording and timing | Prevents duplicate “thinking” speech from the body |
| Autonomous spoken dialogue and curiosity | Prevents two independent idle conversation systems |
| Semantic vision interpretation | Camera hardware is local, but image understanding belongs to the Brain |

## UNO Q body client owns

| Function | Reason |
|---|---|
| Microphone device, raw capture, DSP and endpointing | These depend on the physical microphone and local noise environment |
| Wake phrase and local conversation-session capture | These are latency-sensitive hardware functions |
| Speaker output device and local playback level | These depend on the physical sound device |
| Camera device and frame capture | These depend on the connected camera |
| MCU bridge, GPIO, hardware registry and safety limits | These are physical-body responsibilities |
| Servo trims, directions, mixing, speed/range limits and safe centring | These protect and calibrate the mechanics |
| LED zones, states and speech-envelope animation | These drive the physical LEDs in real time |
| Non-verbal idle motion | Small physical “alive” actions may run locally, but they do not generate dialogue |

## Shared contract

The body sends microphone transcripts, camera frames, body telemetry and user-origin metadata to the Brain. The Brain returns a reply plus validated physical actions. The body then applies hardware limits, performs those actions, plays the Brain-provided speech and reports acknowledgements/telemetry.

## Enforced v10.35 settings

The installer and migration script enforce:

```json
{
  "brain_tts_use_brain_defaults": true,
  "brain_controls_web_memory": true,
  "brain_response_audio_enabled": true,
  "brain_controls_thinking_cues": false,
  "brain_controls_idle_dialogue": true,
  "thinking_cues_enabled": false,
  "thinking_cue_speak": false,
  "voice_command_immediate_cue_enabled": false,
  "idle_life_self_chatter_enabled": false,
  "idle_life_internet_curiosity_enabled": false
}
```

The body web console deliberately omits personality, LLM, memory, internet, Dot.TTS voice and spoken idle-dialogue controls. Those remain in the desktop Brain App. The body controls speaker selection, playback volume, microphone capture and physical mouth animation.
