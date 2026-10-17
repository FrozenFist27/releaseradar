"""SQLite schema, connection helpers and typed queries."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import AlertRecord, CheckResult, FilterDecision

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
  item_key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  target TEXT NOT NULL,
  published_at TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  baseline INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS etags (
  target TEXT PRIMARY KEY,
  etag TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id TEXT NOT NULL,
  target TEXT NOT NULL,
  started_at TEXT NOT NULL,
  duration_ms INTEGER,
  status TEXT NOT NULL,
  http_status INTEGER,
  new_items INTEGER DEFAULT 0,
  rate_remaining INTEGER,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_started ON checks(started_at);
CREATE TABLE IF NOT EXISTS filter_decisions (
  item_key TEXT PRIMARY KEY,
  keep INTEGER,
  reason TEXT,
  summary TEXT,
  model TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  decided_at TEXT
);
CREATE TABLE IF NOT EXISTS pending_alerts (
  item_key TEXT PRIMARY KEY,
  payload_json TEXT,
  attempts INTEGER DEFAULT 0,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
  item_key TEXT PRIMARY KEY,
  channel TEXT,
  published_at TEXT,
  detected_at TEXT,
  alerted_at TEXT,
  latency_s REAL,
  http_status INTEGER
);
CREATE TABLE IF NOT EXISTS health_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT,
  kind TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT
);
CREATE TABLE IF NOT EXISTS baselines (
  target TEXT PRIMARY KEY,
  baselined_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults and apply the schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def db_session(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---- baselines ----
def is_baselined(conn: sqlite3.Connection, target: str) -> bool:
    row = conn.execute("SELECT 1 FROM baselines WHERE target=?", (target,)).fetchone()
    return row is not None


def mark_baselined(conn: sqlite3.Connection, target: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO baselines(target, baselined_at) VALUES(?,?)",
        (target, now_iso()),
    )


# ---- etag cache ----
def get_etag(conn: sqlite3.Connection, target: str) -> str | None:
    row = conn.execute("SELECT etag FROM etags WHERE target=?", (target,)).fetchone()
    return row["etag"] if row else None


def set_etag(conn: sqlite3.Connection, target: str, etag: str | None) -> None:
    conn.execute(
        "INSERT INTO etags(target, etag, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(target) DO UPDATE SET etag=excluded.etag, updated_at=excluded.updated_at",
        (target, etag, now_iso()),
    )


# ---- checks ----
def record_check(conn: sqlite3.Connection, check: CheckResult) -> None:
    conn.execute(
        "INSERT INTO checks(cycle_id,target,started_at,duration_ms,status,http_status,"
        "new_items,rate_remaining,error) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            check.cycle_id,
            check.target,
            check.started_at.isoformat(),
            check.duration_ms,
            check.status,
            check.http_status,
            check.new_items,
            check.rate_remaining,
            check.error,
        ),
    )


# ---- alerts ----
def insert_alert(conn: sqlite3.Connection, rec: AlertRecord) -> bool:
    """Insert an alert row. Returns True if inserted (i.e. first time), False if duplicate."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO alerts(item_key,channel,published_at,detected_at,"
        "alerted_at,latency_s,http_status) VALUES(?,?,?,?,?,?,?)",
        (
            rec.item_key,
            rec.channel,
            rec.published_at.isoformat(),
            rec.detected_at.isoformat(),
            rec.alerted_at.isoformat(),
            rec.latency_s,
            rec.http_status,
        ),
    )
    return cur.rowcount > 0


def alert_exists(conn: sqlite3.Connection, item_key: str) -> bool:
    row = conn.execute("SELECT 1 FROM alerts WHERE item_key=?", (item_key,)).fetchone()
    return row is not None


# ---- filter decisions (cache) ----
def get_filter_decision(conn: sqlite3.Connection, item_key: str) -> FilterDecision | None:
    row = conn.execute("SELECT * FROM filter_decisions WHERE item_key=?", (item_key,)).fetchone()
    if not row:
        return None
    return FilterDecision(
        item_key=row["item_key"],
        keep=bool(row["keep"]),
        reason=row["reason"] or "",
        summary=row["summary"] or "",
        model=row["model"] or "",
        input_tokens=row["input_tokens"] or 0,
        output_tokens=row["output_tokens"] or 0,
    )


def save_filter_decision(conn: sqlite3.Connection, d: FilterDecision) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO filter_decisions(item_key,keep,reason,summary,model,"
        "input_tokens,output_tokens,decided_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            d.item_key,
            1 if d.keep else 0,
            d.reason,
            d.summary,
            d.model,
            d.input_tokens,
            d.output_tokens,
            now_iso(),
        ),
    )


# ---- pending alerts (retry queue) ----
def enqueue_pending(conn: sqlite3.Connection, item_key: str, payload_json: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO pending_alerts(item_key,payload_json,attempts,last_error) "
        "VALUES(?,?,0,NULL)",
        (item_key, payload_json),
    )


def list_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM pending_alerts").fetchall()


def drop_pending(conn: sqlite3.Connection, item_key: str) -> None:
    conn.execute("DELETE FROM pending_alerts WHERE item_key=?", (item_key,))


def bump_pending_attempt(conn: sqlite3.Connection, item_key: str, error: str) -> None:
    conn.execute(
        "UPDATE pending_alerts SET attempts=attempts+1, last_error=? WHERE item_key=?",
        (error, item_key),
    )


# ---- health events ----
def log_health_event(conn: sqlite3.Connection, kind: str, detail: str = "") -> None:
    conn.execute("INSERT INTO health_events(at,kind,detail) VALUES(?,?,?)", (now_iso(), kind, detail))


# ---- small persistent key/value state (watchdog, heartbeat, backoff) ----
def get_kv(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    return row["v"] if row else None


def set_kv(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute("DELETE FROM kv WHERE k=?", (key,))
        return
    conn.execute(
        "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, value),
    )
