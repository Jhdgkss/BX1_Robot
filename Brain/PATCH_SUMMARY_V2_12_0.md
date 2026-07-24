# Robot Brain V2.12.0 — Runtime Workflow and Studios

## Purpose

V2.12 reorganises the main Brain application around day-to-day operation. Personality Studio and Voice Lab are now the authoritative places for character creation and trained voice work, rather than duplicating those editors inside the main window.

## Main workflow

The sidebar is now organised as:

- **Home** — conversation and live status
- **Runtime** — active personality, voice operation, live tools and queued body speech
- **Knowledge** — documents/RAG and robot-profile memory
- **Skills** — bounded behaviour design and approval
- **Body** — telemetry, camera and actions
- **System** — diagnostics, maintenance, voice-service settings, models, API and theme
- **Studios** — launch specialist creation and configuration tools
- **Help** — setup and troubleshooting

## Single ownership model

- Personality Studio owns robot name, role, prompt, trait percentages, GUI theme and personality voice binding.
- Voice Lab owns the active personality's reference recording, transcript and voice benchmark.
- Robot Profiles owns isolated ports, runtime configuration, documents and memory.
- Hardware/body configuration remains separate and safety-authoritative.

The main Runtime page displays and operates these settings without maintaining a second editable copy.

## Runtime identity panel

The header, sidebar, Home page and Runtime page now show:

- active robot name
- active personality project
- independent robot profile
- assigned voice profile and Dot.TTS model
- active GUI theme

Loading a personality refreshes all of these views immediately.

## Voice workflow

The main Runtime page retains only operational controls:

- enable voice output
- speak completed replies
- start/check/stop Dot.TTS
- open Voice Lab
- test active voice
- stop playback

Shared Dot.TTS startup settings have moved to **System → Voice Service**. Personality-owned voice tuning remains in Personality Studio and Voice Lab.

## Memory workflow

Memory controls have moved from the old combined Voice/Memory page to **Knowledge → Memory**. Memory remains attached to the robot profile and is not replaced when a different personality is loaded.

## Capability preparation

The Studios page includes a visible placeholder for the next phase: a permission-controlled Capability Studio where Leo can propose, write, test and request approval to install isolated skills. V2.12 does not yet grant autonomous file, network or command access.
