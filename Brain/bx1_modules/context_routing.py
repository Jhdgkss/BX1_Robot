"""Pure routing guards for local documents and conversational context.

The document library is deliberately conservative: a weak keyword match must
not turn a greeting, a correction, or a live-news request into a manual lookup.
"""
from __future__ import annotations

import re
from typing import List


_ROUTING_STOP_WORDS = {
    "a", "an", "and", "are", "about", "can", "could", "did", "do", "does",
    "for", "from", "going", "have", "hello", "help", "hey", "hi", "how",
    "hows", "i", "im", "in", "is", "it", "just", "latest", "look", "me",
    "much", "my", "new", "news", "of", "on", "please", "really", "said",
    "say", "see", "so", "sorry", "tell", "that", "the", "their", "then",
    "there", "these", "they", "things", "this", "those", "today", "up",
    "want", "was", "we", "were", "what", "whats", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your",
}

_TECHNICAL_TERMS = {
    "alarm", "arduino", "battery", "calibration", "camera", "circuit",
    "connector", "controller", "datasheet", "diagnostic", "drive", "encoder",
    "error", "fault", "firmware", "gpio", "imu", "manual", "motor", "parameter",
    "pinout", "protocol", "register", "robot", "schematic", "sensor", "servo",
    "telemetry", "torque", "voltage", "wiring",
}

_EXPLICIT_DOCUMENT_PATTERNS = (
    r"^/(?:docs?|documents?|manual|rag)\b",
    r"\b(?:local|uploaded|stored|attached)\s+(?:document|documents|file|files|manual|manuals|pdf|pdfs)\b",
    r"\b(?:manual|manuals|datasheet|datasheets|handbook|schematic|wiring diagram|knowledge base|document library)\b",
    r"\b(?:look|check|search|find|read)\s+(?:in|through|inside)?\s*(?:the|my|our)?\s*(?:manual|manuals|documents|docs|pdf|files)\b",
    r"\baccording to\s+(?:the|my|our)?\s*(?:manual|document|datasheet|pdf)\b",
)

_SMALL_TALK_PATTERNS = (
    r"^(?:hi|hello|hey|hiya)(?:\s+there)?$",
    r"^(?:hi|hello|hey)[, ]+(?:how(?:'s| is| are)|hows)\b",
    r"^(?:how(?:'s| is| are)|hows)\s+(?:things|it going|you|your day)\b",
    r"^(?:so\s+)?what(?:'s| is|s)\s+new\??$",
    r"^what(?:'s| is|s)\s+up\??$",
    r"^(?:thanks|thank you|cheers)[.!?]*$",
    r"^(?:sorry[, ]+)?what are you talking about\??$",
    r"^(?:how are you|are you okay|you okay)\??$",
)


def meaningful_query_terms(text: str) -> List[str]:
    """Return useful retrieval terms with conversational filler removed."""
    raw = re.findall(r"[a-z0-9][a-z0-9_.-]*", str(text or "").lower().replace("’", "'"))
    output: List[str] = []
    for term in raw:
        is_code = bool(re.fullmatch(r"(?:0x[0-9a-f]+|[a-z]{1,6}[-_]?\d{2,}[a-z0-9_-]*)", term))
        if (len(term) < 3 and not is_code) or term in _ROUTING_STOP_WORDS or term in output:
            continue
        output.append(term)
    return output[:20]


def requests_local_documents(text: str) -> bool:
    """True only when the user explicitly points at the local document library."""
    low = re.sub(r"\s+", " ", str(text or "").lower().replace("’", "'")).strip()
    return any(re.search(pattern, low) for pattern in _EXPLICIT_DOCUMENT_PATTERNS)


def looks_like_small_talk(text: str) -> bool:
    low = re.sub(r"\s+", " ", str(text or "").lower().replace("’", "'")).strip(" .!")
    if not low:
        return True
    if any(re.search(pattern, low) for pattern in _SMALL_TALK_PATTERNS):
        return True
    meta_phrases = (
        "what do you mean", "why did you say that", "i did not ask", "i didn't ask",
        "thats not what i asked", "that's not what i asked", "change the subject",
    )
    return len(low.split()) <= 12 and any(phrase in low for phrase in meta_phrases)


def contains_live_data_denial(text: str) -> bool:
    """Detect access disclaimers that contradict supplied verified live data."""
    low = re.sub(r"\s+", " ", str(text or "").lower())
    phrases = (
        "don't have access to the internet", "do not have access to the internet",
        "can't access the internet", "cannot access the internet", "unable to access the internet",
        "don't have real-time access", "do not have real-time access", "cannot access real-time",
        "cannot directly access", "can't directly access", "unable to directly access",
        "cannot browse", "can't browse", "unable to browse", "not able to browse",
        "not connected to live", "not connected to the bbc", "not connected to bbc",
        "not connected to live bbc feeds", "i'm not connected", "i am not connected",
        "knowledge is based on",
    )
    if any(phrase in low for phrase in phrases):
        return True
    return bool(re.search(
        r"\b(?:cannot|can't|unable to|not able to)\b.{0,55}\b(?:access|browse|connect)\b.{0,55}\b(?:internet|web|bbc|site|feed|live|real-time)\b",
        low,
    ))


def strip_live_data_denial_sentences(text: str) -> str:
    """Remove only contradictory disclaimer sentences, preserving sourced facts."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", str(text or "").strip())
    kept = [part.strip() for part in parts if part.strip() and not contains_live_data_denial(part)]
    return "\n\n".join(kept).strip()


def claims_unverified_robot_observation(text: str) -> bool:
    """Spot claims that the Brain inspected logs/telemetry without evidence."""
    low = re.sub(r"\s+", " ", str(text or "").lower())
    patterns = (
        r"\b(?:i|we)\s+(?:have\s+|had\s+|just\s+|also\s+)*(?:noticed|detected|observed|saw|checked|read|found)\b.{0,100}\b(?:logs?|diagnostics?|telemetry|sensors?|system status)\b",
        r"\b(?:i'm|i am|we're|we are)\s+(?:just\s+)?(?:running|checking|monitoring|watching)\s+(?:the\s+)?(?:(?:usual|routine|standard)\s+)?(?:diagnostics?|logs?|telemetry|sensors?|system status)\b",
        r"\b(?:the|my|our)\s+(?:logs?|diagnostics?|telemetry|sensors?)\s+(?:show|showed|report|reported|indicate|indicated|contain|contained)\b",
        r"\b(?:error|fault|alarm)\s+codes?\s+(?:popping up|appeared|showed up|in (?:the|my|our) logs?|were detected)\b",
        r"\b(?:everything|the system|my systems?|all systems?)\s+(?:seems?|looks?|is|are)\s+(?:stable|normal|healthy|fine|nominal|online|operational)\b",
    )
    return any(re.search(pattern, low) for pattern in patterns)


def should_retrieve_local_documents(
    text: str,
    *,
    live_route: str = "none",
    relevance_gate: bool = True,
) -> bool:
    """Decide whether automatic local-document retrieval is justified."""
    query = str(text or "").strip()
    if not query:
        return False
    if not relevance_gate:
        return True
    if requests_local_documents(query):
        return True
    if str(live_route or "none").lower() not in {"", "none"}:
        return False
    if looks_like_small_talk(query):
        return False

    low = query.lower().replace("’", "'")
    terms = meaningful_query_terms(query)
    has_code = bool(re.search(r"\b(?:0x[0-9a-f]+|[a-z]{1,6}[-_]?\d{2,}[a-z0-9_-]*)\b", low))
    if has_code or any(term in _TECHNICAL_TERMS for term in terms):
        return True

    # Permit broad document collections (recipes, policies, project notes, and
    # so on) when the request is a substantive question. The document index
    # still has to return an actual term match before context is injected.
    question_or_request = "?" in query or bool(re.search(r"\b(?:explain|describe|compare|find|show|list|how|why|where|when|which)\b", low))
    return question_or_request and len(terms) >= 3
