from __future__ import annotations

from dataclasses import dataclass
from typing import List

from bx1_ui.page_registry import PageRegistry


@dataclass
class NavigationState:
    registry: PageRegistry
    active_page_id: str = "home"
    collapsed: bool = False

    def select(self, page_id_or_alias: str) -> str:
        page_id = self.registry.canonical_id(page_id_or_alias)
        page = self.registry.get(page_id)
        if not page.available:
            raise ValueError(page.unavailable_reason or f"Page unavailable: {page_id}")
        self.active_page_id = page.page_id
        return self.active_page_id

    def toggle_collapsed(self) -> bool:
        self.collapsed = not self.collapsed
        return self.collapsed

    def visible_labels(self) -> List[str]:
        if self.collapsed:
            return [page.icon for page in self.registry.pages()]
        return [f"{page.icon} {page.display_name}" for page in self.registry.pages()]

