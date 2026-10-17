"""Health watchdog, heartbeat and Healthchecks.io dead-man switch ping."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from .db import log_health_event


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Watchdog:
    """Tracks consecutive failures and fires a loud alert past a threshold."""

    fail_alert_after_s: int = 300
    rearm_interval_s: int = 1800
    failing_since: datetime | None = None
    last_alert_at: float | None = None
    alerted: bool = False
    events: list[str] = field(default_factory=list)
    last_outage_min: float = 0.0

    # --- persistence so the watchdog survives one-shot (systemd timer) runs ---
    def to_json(self) -> str:
        return json.dumps(
            {
                "failing_since": self.failing_since.isoformat() if self.failing_since else None,
                "last_alert_at": self.last_alert_at,
                "alerted": self.alerted,
            }
        )

    def load_json(self, raw: str | None) -> None:
        if not raw:
            return
        try:
            d = json.loads(raw)
            fs = d.get("failing_since")
            self.failing_since = datetime.fromisoformat(fs) if fs else None
            self.last_alert_at = d.get("last_alert_at")
            self.alerted = bool(d.get("alerted"))
        except Exception:
            pass

    def record_success(self) -> list[str]:
        """Return any recovery events to emit; clears failure state."""
        out: list[str] = []
        if self.alerted and self.failing_since:
            mins = (_now() - self.failing_since).total_seconds() / 60
            self.last_outage_min = mins
            out.append("recovery")
            self.events.append(f"recovered_after_{mins:.1f}min")
        self.failing_since = None
        self.alerted = False
        return out

    def record_failure(self, error: str, target: str) -> list[str]:
        """Return loud-alert event text if we should alert now (once per rearm)."""
        if self.failing_since is None:
            self.failing_since = _now()
        elapsed = (_now() - self.failing_since).total_seconds()
        if elapsed < self.fail_alert_after_s:
            return []
        now = time.time()
        if self.alerted and self.last_alert_at and (now - self.last_alert_at) < self.rearm_interval_s:
            return []
        self.alerted = True
        self.last_alert_at = now
        mins = elapsed / 60
        self.events.append(f"failure_alert_at_{mins:.1f}min")
        return [f"failure:{mins:.1f}min:{target}:{error}"]


def ping_healthchecks(url: str, client: httpx.Client | None = None, timeout: float = 10.0) -> bool:
    """Ping the Healthchecks.io dead-man switch. Returns True on 2xx."""
    if not url:
        return False
    c = client or httpx.Client(timeout=timeout)
    try:
        r = c.get(url)
        return r.status_code < 300
    except Exception:
        return False
    finally:
        if client is None:
            c.close()


def heartbeat_summary(conn, since_iso: str | None = None) -> str:
    """Build a heartbeat line from the checks table."""
    if since_iso:
        row = conn.execute(
            "SELECT COUNT(*) n, SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) errs "
            "FROM checks WHERE started_at > ?",
            (since_iso,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) n, SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) errs FROM checks"
        ).fetchone()
    n = row["n"] or 0
    errs = row["errs"] or 0
    return f"ReleaseRadar alive — {n} checks, {errs} errors since {since_iso or 'start'}."


def record_health_event(conn, kind: str, detail: str = "") -> None:
    log_health_event(conn, kind, detail)
