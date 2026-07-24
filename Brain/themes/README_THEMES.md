# Robot Brain Themes

The PyQt app loads theme presets from `themes/*.json` at startup.

Each theme entry must use the internal Robot Brain keys, for example:

```json
{
  "my_custom_theme": {
    "bg0": "#183653",
    "bg1": "#0b1118",
    "bg2": "#05080c",
    "panel": "rgba(16, 27, 39, 235)",
    "border": "#26394d",
    "text": "#dce8f4",
    "muted": "#8fa5ba",
    "title": "#eef7ff",
    "input": "#07101a",
    "input2": "#09131e",
    "accent": "#1d75aa",
    "accent2": "#31d07d",
    "primary0": "#1e6947",
    "primary1": "#123727",
    "danger0": "#722735",
    "danger1": "#3b141d",
    "tab": "#101b27",
    "tab_selected": "#1d3c58",
    "hint_bg": "#07131e",
    "hint_border": "#24415a",
    "pill": "#09131e",
    "pill_text": "#8fe7ff",
    "warn": "#ffca3a"
  }
}
```

Add a new JSON file here, restart the app, and the theme should appear in Settings.
