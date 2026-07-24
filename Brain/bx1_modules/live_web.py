"""Pure helpers for broad web routing and display-only source attribution."""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bx1_modules.context_routing import looks_like_small_talk, meaningful_query_terms, requests_local_documents


_SOURCE_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:sources?\s*\(not spoken\)|sources?\s+used|information sources?|references?)\s*:?\s*$"
)


def looks_like_general_web_research(text: str) -> bool:
    """Return True when an external search is likely to improve a factual answer.

    This intentionally excludes greetings, local-document requests, creative
    writing and explicit physical robot commands. It is broader than the
    current-data router: stable technical and explanatory questions qualify.
    """
    raw = str(text or "").strip()
    low = re.sub(r"\s+", " ", raw.lower().replace("’", "'")).strip()
    if not low or looks_like_small_talk(low) or requests_local_documents(low):
        return False

    # These requests are better answered from the conversation/model rather
    # than delayed by a search that cannot materially improve the result.
    non_research_starts = (
        "write ", "rewrite ", "reword ", "draft ", "translate ", "proofread ",
        "summarise this", "summarize this", "make this ", "create a story",
        "tell me a joke", "say hello", "repeat ", "remember ", "forget ",
    )
    if low.startswith(non_research_starts):
        return False

    # Distinguish commands to the embodied robot from questions about hardware.
    command_text = re.sub(r"^(?:(?:can|could|would|will)\s+you\s+|please\s+)", "", low)
    robot_action = re.search(
        r"^(?:look|move|drive|turn|stop|tilt|nod|shake|raise|lower|set|switch|light|blink)\b",
        command_text,
    )
    if robot_action and re.search(r"\b(?:head|eyes?|servo|motor|wheel|robot|led|mouth|camera)\b", low):
        return False

    # Personal/conversational questions should use memory and dialogue context.
    if re.search(r"\b(?:how are you|how do you feel|do you remember me|what is my name|who am i|can you help me|what can you do)\b", low):
        return False

    if re.match(
        r"^(?:(?:can|could|would|will)\s+you\s+)?(?:write|rewrite|reword|draft|translate|proofread|summarise|summarize|repeat|remember|forget)\b",
        low,
    ):
        return False

    research_openers = (
        "what ", "what's ", "whats ", "who ", "where ", "when ", "why ",
        "how ", "which ", "is ", "are ", "does ", "do ", "did ", "can ",
        "could ", "would ", "should ", "will ", "explain ", "describe ",
        "compare ", "recommend ", "research ", "find ", "tell me about ",
        "give me information", "check ", "verify ",
    )
    if "?" in raw or low.startswith(research_openers):
        return True

    # Substantive noun-heavy prompts such as "PID tuning methods" also qualify.
    terms = meaningful_query_terms(low)
    return len(terms) >= 4


def _known_source_url(name: str) -> str:
    low = str(name or "").lower()
    if "open-meteo" in low:
        return "https://open-meteo.com/"
    if "aviation weather" in low:
        return "https://aviationweather.gov/"
    if "met office" in low:
        return "https://www.metoffice.gov.uk/"
    if "duckduckgo" in low:
        return "https://duckduckgo.com/"
    if "google programmable" in low:
        return "https://programmablesearchengine.google.com/"
    return ""


def extract_live_source_entries(context: str, max_entries: int = 10) -> List[Dict[str, str]]:
    """Extract structured source records from BX1 live-tool context blocks."""
    value = str(context or "")
    entries: List[Dict[str, str]] = []
    seen: set[str] = set()

    block_re = re.compile(r"(?ms)^\[(\d+)\]\s+([^\n]+)\n(.*?)(?=^\[\d+\]\s+|\Z)")
    for match in block_re.finditer(value):
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        body = match.group(3)
        source_match = re.search(r"(?m)^Source:\s*([^\n]+)", body)
        url_match = re.search(r"(?m)^URL:\s*(https?://\S+)", body)
        source = re.sub(r"\s+", " ", source_match.group(1)).strip() if source_match else ""
        url = url_match.group(1).rstrip(".,);]") if url_match else ""
        if not source and url:
            source = urlparse(url).netloc.removeprefix("www.")
        key = url.lower() or f"{title.lower()}|{source.lower()}"
        if not key or key in seen:
            continue
        seen.add(key)
        entries.append({"title": title[:240], "source": source[:160], "url": url[:1000]})
        if len(entries) >= max_entries:
            return entries

    # Weather and aviation contexts often cite a service without numbered rows.
    for match in re.finditer(r"(?m)^Source:\s*([^\n]+)", value):
        source = re.sub(r"\s+", " ", match.group(1)).strip()
        source = source.split(". These ", 1)[0].strip().rstrip(".")
        if not source:
            continue
        if any(source.lower() == entry.get("source", "").lower() for entry in entries):
            continue
        url = _known_source_url(source)
        key = url.lower() or source.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append({"title": source[:240], "source": source[:160], "url": url})
        if len(entries) >= max_entries:
            return entries

    if not entries:
        provider = re.search(r"(?m)^Provider:\s*([^\n]+)", value)
        if provider:
            source = re.sub(r"\s+", " ", provider.group(1)).strip()
            entries.append({"title": source, "source": source, "url": _known_source_url(source)})
    return entries


def source_names(entries: List[Dict[str, str]]) -> List[str]:
    output: List[str] = []
    for entry in entries:
        name = str(entry.get("source") or entry.get("title") or "").strip()
        if name and name not in output:
            output.append(name)
    return output


def strip_sources_for_speech(text: str) -> str:
    """Remove citations, source footers and URLs before TTS synthesis."""
    value = str(text or "")
    heading = _SOURCE_HEADING_RE.search(value)
    if heading:
        value = value[: heading.start()]
    value = re.sub(r"\s*\((?:source|sources|reference|references)\s*:\s*[^)]*\)", "", value, flags=re.I)
    value = re.sub(r"\s*\[(?:source|sources|reference|references)\s*:\s*[^]]*\]", "", value, flags=re.I)
    value = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"(?<!\w)\[(?:\d+|\d+(?:\s*,\s*\d+)+)\](?!\w)", "", value)
    value = re.sub(r"(?i)\baccording to\s+[^,.;:]{2,100},\s*", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
    return value.strip()


def append_live_sources_to_reply(
    reply: str,
    diagnostics: Dict[str, Any],
    *,
    enabled: bool = True,
    max_sources: int = 6,
) -> str:
    """Append a deterministic, display-only source footer to a visible reply."""
    answer = str(reply or "").strip()
    if not enabled or not bool((diagnostics or {}).get("verified")):
        return answer
    entries = list((diagnostics or {}).get("source_entries") or [])[: max(1, int(max_sources or 6))]
    if not entries:
        return answer
    # Avoid accumulating a second footer when a reply is repaired or repeated.
    existing = _SOURCE_HEADING_RE.search(answer)
    if existing:
        answer = answer[: existing.start()].rstrip()
    lines = ["Sources (not spoken):"]
    for index, entry in enumerate(entries, start=1):
        title = str(entry.get("title") or entry.get("source") or "Source").strip()
        source = str(entry.get("source") or "").strip()
        url = str(entry.get("url") or "").strip()
        label = title if not source or source.lower() in title.lower() else f"{title} — {source}"
        lines.append(f"{index}. {label}")
        if url:
            lines.append(f"   {url}")
    return answer + "\n\n" + "\n".join(lines)
