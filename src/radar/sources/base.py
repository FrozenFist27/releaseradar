"""Source protocol."""

from __future__ import annotations

from typing import Protocol

from ..models import FetchResult


class Source(Protocol):
    def fetch(self, target: str) -> FetchResult: ...
