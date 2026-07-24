BX1 ROBOT BRAIN V2.9.0 - WEB RESEARCH AND SILENT SOURCES
========================================================

WHAT CHANGED
------------
1. BX1 can now search the internet for ordinary factual and technical questions,
   not only prompts containing words such as "latest", "news" or "search".
2. Verified sources are appended to the visible answer under:

       Sources (not spoken):

3. The source list, URLs and citation markers are removed before Dot.TTS or Edge
   receives the text. The physical robot therefore speaks the answer only.
4. Local memory and relevant uploaded documents can still contribute alongside
   a general web lookup.

LIVE TOOLS SETTINGS
-------------------
Open Live Tools and keep these enabled:

- Enable web/live data
- Auto route when prompt needs current data
- Use web to improve general factual answers
- Append sources to the on-screen reply

Leave "Speak source lists and URLs" unticked. It is disabled by default.

SEARCH PROVIDERS
----------------
- Without credentials, BX1 uses DuckDuckGo fallback search.
- For more reliable results, select Google CSE and enter a Google Programmable
  Search API key plus Search Engine ID in Live Tools.
- News uses current RSS feeds.
- Weather uses Open-Meteo, with optional Met Office DataHub support.
- METAR/TAF uses the US Aviation Weather Center API.

API RESPONSE
------------
/api/chat now returns:

- reply: visible answer including the display-only source footer
- answer: answer text without the appended source footer
- speech: source-free text intended for TTS
- sources: structured source title/source/URL records

INSTALLATION
------------
Close Robot Brain and Dot.TTS, then copy this release over the existing Brain
project. Existing runtime data, personalities, memory, documents and voice files
are retained when merging rather than deleting the runtime folders.
