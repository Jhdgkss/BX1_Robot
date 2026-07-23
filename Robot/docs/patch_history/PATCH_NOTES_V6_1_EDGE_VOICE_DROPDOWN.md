# BX1 Arduino Q Client v6.1 — Edge Voice Dropdown Fix

This patch fixes the Speech / Volume Settings web page so the Edge TTS voice selector is a real drop-down list instead of a free text box.

## Important

This patch zip is structured to be extracted directly inside the existing `Arduino_Q_Client_V1` folder.

After applying the patch, restart the web app:

```bash
cd ~/Arduino_Q_Client_V1
./START_BX1_WEB.sh
```

Then hard-refresh the browser page:

```text
Ctrl + F5
```

Open:

```text
http://BX1.local:8088
```

## What changed

- Edge voice field is now a true `<select>` drop-down.
- Added grouped British, Irish, Australian and US Edge voices.
- Added a page version marker: `BX1 Web Control v6.1`.
- Strengthened no-cache headers so the browser is less likely to show the old page.
- If the Edge field still looks like a typing box, the old `python/web_control.py` is still running or the browser is cached.

## Files updated

- `python/web_control.py`
- `PATCH_NOTES_V6_1_EDGE_VOICE_DROPDOWN.md`
