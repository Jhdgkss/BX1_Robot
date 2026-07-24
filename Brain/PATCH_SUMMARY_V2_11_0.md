# Robot Brain V2.11.0 patch summary

## Personality Studio

A separate **Personality Studio** window now manages complete character projects without mixing them with hardware settings.

Each project contains:

- project name and description
- robot name, role, subtitle and identity style
- personality prompt and control sliders
- GUI theme
- selected voice profile and voice delivery settings
- a personality-specific Dot.TTS voice namespace

The Studio supports create, edit, duplicate, delete, load, import and export.

## Portable personality files

Personality projects can be exported as a single `.bxpersonality` file and imported on another Robot Brain installation. The package includes the character settings, GUI theme, embedded selected voice profile and available voice reference assets.

## Voice binding

The Dot.TTS Voice Lab is now opened in a separate namespace for each personality. A reference recording and exact transcript generated in the Lab return automatically whenever that personality is loaded.

Existing robot-profile voice references are migrated to the current personality on first use. Hardware, API ports, memory, documents and safety limits remain outside personality files.

## GUI identity

Loading a personality now updates the robot name, window title, headers, conversation identity, wake-name publishing, selected GUI theme and voice configuration together.
