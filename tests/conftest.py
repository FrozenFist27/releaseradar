"""Shared pytest fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from radar.db import connect
from radar.models import Item

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_db(tmp_path):
    conn = connect(tmp_path / "radar.db")
    yield conn
    conn.close()


@pytest.fixture
def sample_items():
    now = datetime.now(UTC)
    return [
        Item(
            source="github_releases",
            target="octo/repo",
            item_id="101",
            title="v1.0.0",
            url="https://github.com/octo/repo/releases/101",
            published_at=now,
            author="octo",
            fields={"tag_name": "v1.0.0", "prerelease": "False"},
            body_excerpt="First release",
        ),
        Item(
            source="github_releases",
            target="octo/repo",
            item_id="102",
            title="v1.1.0",
            url="https://github.com/octo/repo/releases/102",
            published_at=now,
            author="octo",
            fields={"tag_name": "v1.1.0", "prerelease": "False"},
            body_excerpt="Second release",
        ),
    ]


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
