from __future__ import annotations

from dataclasses import dataclass
from typing import List

from bx1_ui.page_registry import PageDefinition, PageRegistry


@dataclass(frozen=True)
class CommandMatch:
    page: PageDefinition
    score: int
    reason: str


class CommandPaletteIndex:
    def __init__(self, registry: PageRegistry) -> None:
        self.registry = registry

    def search(self, query: str, *, include_unavailable: bool = True, limit: int = 8) -> List[CommandMatch]:
        terms = [term for term in str(query or "").lower().split() if term]
        if not terms:
            return [CommandMatch(page, 1, "top-level page") for page in self.registry.pages()[:limit]]
        matches: List[CommandMatch] = []
        for page in self.registry.pages():
            if not include_unavailable and not page.available:
                continue
            haystack = page.searchable_text()
            score = sum(4 if term == page.page_id.lower() else 1 for term in terms if term in haystack)
            if score:
                reason = "available" if page.available else page.unavailable_reason or "unavailable"
                matches.append(CommandMatch(page, score, reason))
        matches.sort(key=lambda item: (-item.score, item.page.display_name))
        return matches[:limit]

