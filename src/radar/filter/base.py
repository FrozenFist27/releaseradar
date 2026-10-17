"""Filter protocol."""

from __future__ import annotations

from typing import Protocol

from ..models import FilterDecision, Item


class Filter(Protocol):
    def decide(self, item: Item) -> FilterDecision: ...
