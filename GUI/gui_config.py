"""
BX1 GUI VISUAL CONFIGURATION
============================

Edit this file to change GUI asset locations.

The icon files are NOT selected from the Settings page by design.
Relative paths are resolved from the BX1_Dev project folder.

PNG is recommended. Transparent backgrounds work best.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# CHAT PROCESSING ICONS
# ------------------------------------------------------------------

THINKING_ICON = PROJECT_ROOT / "GUI" / "icons" / "thinking.png"
GENERATING_AUDIO_ICON = PROJECT_ROOT / "GUI" / "icons" / "generating_audio.png"
PLAYING_AUDIO_ICON = PROJECT_ROOT / "GUI" / "icons" / "playing_audio.png"

# Icon sizes in pixels.
CHAT_MESSAGE_STATUS_ICON_SIZE = 16
CHAT_BOTTOM_STATUS_ICON_SIZE = 20

# Fallback text is shown if an icon file does not exist yet.
THINKING_FALLBACK = "💭"
GENERATING_AUDIO_FALLBACK = "🎙"
PLAYING_AUDIO_FALLBACK = "🔊"

THINKING_TEXT = "Thinking"
GENERATING_AUDIO_TEXT = "Generating audio"
PLAYING_AUDIO_TEXT = "Playing audio"
