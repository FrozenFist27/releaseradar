"""De-duplication: the core 'never the same alert twice' guarantee.

Identity is source + ':' + stable_id (e.g. the GitHub release's numeric `id`).
Items are written to `seen_items` with INSERT OR IGNORE BEFORE any alert is
attempted, so a crash between 'seen' and 'alerted' can never cause a duplicate
detection. The `alerts` table's PRIMARY KEY on item_key is a second, hard guard.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .models import Item


def _now() -> str:
    return datetime.now(UTC).isoformat()


def mark_new(conn: sqlite3.Connection, items: list[Item], baseline: bool = False) -> list[Item]:
    """Insert unseen items. Return only those that were actually new.

    baseline=True marks items as baseline (seen but never alerted) on first run.
    """
    new: list[Item] = []
    detected = _now()
    for it in items:
        cur = conn.execute(
            "INSERT OR IGNORE INTO seen_items(item_key,source,target,published_at,"
            "detected_at,baseline) VALUES(?,?,?,?,?,?)",
            (it.key, it.source, it.target, it.published_at.isoformat(), detected, 1 if baseline else 0),
        )
        if cur.rowcount > 0 and not baseline:
            new.append(it)
    return new


def is_seen(conn: sqlite3.Connection, item_key: str) -> bool:
    row = conn.execute("SELECT 1 FROM seen_items WHERE item_key=?", (item_key,)).fetchone()
    return row is not None
