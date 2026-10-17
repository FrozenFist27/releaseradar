"""Structured events must land in the daily JSONL file (used by the duplicate audit)."""

from __future__ import annotations

import json

from radar.logging_setup import get_logger, setup_logging


def test_events_written_to_jsonl_file(tmp_path):
    path = setup_logging(tmp_path)
    get_logger("t").info("alert_sent", item_key="k1", latency_s=1.5)
    import logging

    for h in logging.getLogger().handlers:
        h.flush()
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    assert any(d.get("event") == "alert_sent" and d.get("item_key") == "k1" for d in lines)
