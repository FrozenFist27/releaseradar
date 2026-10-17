"""Notifier protocol."""

from __future__ import annotations

from typing import Protocol

from ..models import FilterDecision, Item


class Notifier(Protocol):
    def send_item(self, item: Item, decision: FilterDecision | None = None) -> int: ...
    def send_text(self, content: str) -> int: ...
