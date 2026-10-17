"""No-op filter: keeps everything (used when LLM filtering is disabled)."""

from __future__ import annotations

from ..models import FilterDecision, Item


class NoopFilter:
    def decide(self, item: Item) -> FilterDecision:
        return FilterDecision(
            item_key=item.key,
            keep=True,
            reason="filter disabled",
            summary="",
            model="none",
        )
