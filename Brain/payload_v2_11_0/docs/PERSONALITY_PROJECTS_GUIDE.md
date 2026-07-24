# Personality Projects Guide

## Opening Personality Studio

Start Robot Brain, open **Robot → Identity / Personality**, then press **Open Personality Studio**.

The left side lists saved personality projects. The right side edits the selected project in three areas:

1. **Identity & Appearance** — project name, robot name, role, subtitle, identity style, gender and GUI theme.
2. **Character** — personality controls, style strength and the LLM personality prompt.
3. **Voice** — voice profile, TTS engine, Dot.TTS model, Edge fallback, voice direction and test phrase.

## Creating a personality

Press **New**, enter a project name, edit the identity, character and voice settings, then press **Save Changes**. Press **Load into Brain** to make it active.

Loading changes the robot name and GUI theme immediately. The same name is used by the Brain API and published wake phrases.

## Training or cloning a voice

Select the personality and open the **Voice** tab. Press **Open / Train Voice**.

The Dot.TTS Voice Lab displays the selected personality name. Upload a clean reference recording and enter the exact words spoken in that recording. Generate a test sample. Dot.TTS stores that reference under a personality-specific namespace.

Return to Robot Brain and press **Save and Test Voice**. Loading another personality changes to its own saved voice namespace.

## Exporting and importing

Press **Export File** to create a `.bxpersonality` package. The package contains the personality settings, GUI theme, selected voice profile and voice assets that are accessible to Robot Brain.

Press **Import File** on another installation to add the project. Imported voice assets are installed into that robot profile's runtime personality-assets folder.

## Safety separation

Personality files do not contain servo limits, GPIO mappings, IMU settings, wheel-drive settings, API ports, memory databases or document libraries. Those remain owned by the physical robot profile.
