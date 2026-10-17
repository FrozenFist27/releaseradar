"""De-duplication: same items twice, reorder, add, restart."""

from __future__ import annotations

from datetime import UTC

from radar.db import connect
from radar.dedupe import is_seen, mark_new


def test_same_items_twice(tmp_db, sample_items):
    first = mark_new(tmp_db, sample_items)
    tmp_db.commit()
    assert len(first) == 2
    second = mark_new(tmp_db, sample_items)
    tmp_db.commit()
    assert second == []


def test_reordered_list_zero_new(tmp_db, sample_items):
    mark_new(tmp_db, sample_items)
    tmp_db.commit()
    reordered = list(reversed(sample_items))
    assert mark_new(tmp_db, reordered) == []


def test_one_added_id(tmp_db, sample_items):
    mark_new(tmp_db, sample_items)
    tmp_db.commit()
    from datetime import datetime

    from radar.models import Item

    extra = Item(
        source="github_releases",
        target="octo/repo",
        item_id="103",
        title="v1.2.0",
        url="https://github.com/octo/repo/releases/103",
        published_at=datetime.now(UTC),
    )
    new = mark_new(tmp_db, sample_items + [extra])
    tmp_db.commit()
    assert len(new) == 1
    assert new[0].item_id == "103"


def test_restart_new_connection(tmp_db, sample_items, tmp_path):
    mark_new(tmp_db, sample_items)
    tmp_db.commit()
    dbfile = tmp_path / "radar.db"
    # Reopen a fresh connection to the same file (simulates process restart).
    conn2 = connect(dbfile)
    try:
        assert mark_new(conn2, sample_items) == []
        assert is_seen(conn2, "github_releases:101")
    finally:
        conn2.close()


def test_baseline_marks_seen_but_returns_no_new(tmp_db, sample_items):
    new = mark_new(tmp_db, sample_items, baseline=True)
    tmp_db.commit()
    assert new == []
    assert is_seen(tmp_db, "github_releases:101")
