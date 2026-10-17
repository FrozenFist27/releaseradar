#!/usr/bin/env python3
"""Run the LLM filter over tests/fixtures/filter_eval.jsonl (30 synthetic, hand-labelled items).

Makes ONE API call per item (max_tokens=200) and prints accuracy, false negatives and cost.
Usage:  python scripts/eval_filter.py [--out docs/filter_eval.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar.filter.llm import AnthropicFilter  # noqa: E402
from radar.models import Item  # noqa: E402

PRICE_IN, PRICE_OUT = 0.10, 0.50  # USD per MTok, claude-haiku-5-5 (<100K context)
CRITERIA = "Alert only for releases with security fixes, breaking changes, or new major features."


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/filter_eval.json")
    args = ap.parse_args()
    load_dotenv()
    f = AnthropicFilter(os.environ["ANTHROPIC_API_KEY"], os.environ.get("LLM_MODEL", "claude-haiku-5-5"), CRITERIA)
    rows = [json.loads(x) for x in Path("tests/fixtures/filter_eval.jsonl").read_text(encoding="utf-8").splitlines() if x]
    tp = tn = fp = fn = tin = tout = errs = 0
    err_reasons: list[str] = []
    for i, r in enumerate(rows):
        item = Item(source="github_releases", target="synthetic/repo", item_id=str(i), title=r["title"],
                    url=f"https://example.com/{i}", published_at=datetime.now(UTC), body_excerpt=r["body"],
                    fields={"tag_name": r["title"]})
        d = f.decide(item)
        tin += d.input_tokens
        tout += d.output_tokens
        if d.reason.startswith("filter_"):
            errs += 1
            err_reasons.append(d.reason)
        pred = "keep" if d.keep else "skip"
        if r["label"] == "keep":
            tp += pred == "keep"
            fn += pred == "skip"
        else:
            tn += pred == "skip"
            fp += pred == "keep"
    n = len(rows)
    out = {"n": n, "accuracy": round((tp + tn) / n, 4), "false_negatives": fn, "false_positives": fp,
           "fail_open_errors": errs, "fail_open_reasons": err_reasons, "input_tokens": tin, "output_tokens": tout, "model": f.model,
           "cost_usd": round((tin * PRICE_IN + tout * PRICE_OUT) / 1e6, 6)}
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
