from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set


PageFactory = Callable[[], object]


@dataclass(frozen=True)
class PageDefinition:
    page_id: str
    display_name: str
    icon: str
    category: str
    keywords: tuple[str, ...] = ()
    classification: str = "basic"
    factory: Optional[PageFactory] = None
    aliases: tuple[str, ...] = ()
    available: bool = True
    unavailable_reason: str = ""
    shortcut_actions: tuple[str, ...] = ()

    def searchable_text(self) -> str:
        parts = [self.page_id, self.display_name, self.category, self.classification]
        parts.extend(self.keywords)
        parts.extend(self.aliases)
        parts.extend(self.shortcut_actions)
        return " ".join(str(part).lower() for part in parts if part)


class PageRegistry:
    def __init__(self) -> None:
        self._pages: Dict[str, PageDefinition] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, page: PageDefinition) -> None:
        if page.page_id in self._pages:
            raise ValueError(f"Duplicate page id: {page.page_id}")
        aliases = {alias for alias in page.aliases if alias}
        collisions = aliases.intersection(self._aliases)
        if collisions:
            raise ValueError(f"Duplicate page alias: {sorted(collisions)[0]}")
        self._pages[page.page_id] = page
        for alias in aliases:
            self._aliases[alias] = page.page_id

    def get(self, page_id_or_alias: str) -> PageDefinition:
        key = str(page_id_or_alias or "")
        key = self._aliases.get(key, key)
        return self._pages[key]

    def pages(self) -> List[PageDefinition]:
        return list(self._pages.values())

    def page_ids(self) -> List[str]:
        return list(self._pages.keys())

    def canonical_id(self, page_id_or_alias: str) -> str:
        key = str(page_id_or_alias or "")
        return self._aliases.get(key, key)

    def duplicate_routes(self) -> Dict[str, List[str]]:
        seen: Dict[str, List[str]] = {}
        for page in self._pages.values():
            for term in page.aliases:
                seen.setdefault(term, []).append(page.page_id)
        return {term: ids for term, ids in seen.items() if len(ids) > 1}


def assert_unique_pages(pages: Iterable[PageDefinition]) -> None:
    ids: Set[str] = set()
    aliases: Set[str] = set()
    for page in pages:
        if page.page_id in ids:
            raise ValueError(f"Duplicate page id: {page.page_id}")
        ids.add(page.page_id)
        for alias in page.aliases:
            if alias in aliases:
                raise ValueError(f"Duplicate page alias: {alias}")
            aliases.add(alias)

