"""Anthropic LLM filter with prompt caching, strict JSON parsing and fail-open."""

from __future__ import annotations

import json
import re

from ..models import FilterDecision, Item
from .prompts import SYSTEM_PROMPT, build_user_message

# Cache the small system prompt across calls (Anthropic prompt caching).
_CACHE = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
MAX_TOKENS = 200
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class AnthropicFilter:
    def __init__(self, api_key: str, model: str, criteria: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.criteria = criteria

    def decide(self, item: Item) -> FilterDecision:
        user_msg = build_user_message(self.criteria, item)
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=_CACHE,
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception as e:  # network/SDK errors -> fail open
            return FilterDecision(
                item_key=item.key,
                keep=True,
                reason=f"filter_error: {type(e).__name__}",
                summary="",
                model=self.model,
            )

        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        in_tok = getattr(resp.usage, "input_tokens", 0)
        out_tok = getattr(resp.usage, "output_tokens", 0)

        parsed = _parse_json(text)
        if parsed is None:  # parse failure -> fail open
            return FilterDecision(
                item_key=item.key,
                keep=True,
                reason="filter_parse_error",
                summary="",
                model=self.model,
                input_tokens=in_tok,
                output_tokens=out_tok,
            )
        keep = bool(parsed.get("keep", True))
        return FilterDecision(
            item_key=item.key,
            keep=keep,
            reason=str(parsed.get("reason", ""))[:200],
            summary=str(parsed.get("summary", ""))[:280],
            model=self.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def build_filter(provider: str, api_key: str, model: str, criteria: str):
    """Factory: returns an AnthropicFilter, or None when filtering is off."""
    if provider == "anthropic" and api_key:
        return AnthropicFilter(api_key=api_key, model=model, criteria=criteria)
    return None
