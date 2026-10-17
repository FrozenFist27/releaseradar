"""The scheduler: fetch -> dedupe -> filter -> alert -> health.

`run_once()` is one complete poll cycle and keeps ALL cross-cycle state in SQLite
(ETags, baselines, watchdog, heartbeat clock, rate-limit backoff). That makes it safe to
drive either from the built-in loop (`radar run`) or from a systemd timer
(`radar once` every 30 s), which is how the VM deployment runs.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from datetime import UTC, datetime

from .config import Config
from .db import (
    bump_pending_attempt,
    db_session,
    drop_pending,
    enqueue_pending,
    get_filter_decision,
    get_kv,
    insert_alert,
    is_baselined,
    list_pending,
    mark_baselined,
    record_check,
    save_filter_decision,
    set_kv,
)
from .dedupe import mark_new
from .filter.llm import build_filter
from .health import Watchdog, heartbeat_summary, ping_healthchecks, record_health_event
from .http import build_client
from .logging_setup import get_logger
from .models import AlertRecord, CheckResult, Item
from .notify.discord import DiscordNotifier
from .sources.github_releases import API, GithubReleasesSource

log = get_logger("radar.scheduler")


def _now() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    def __init__(self, cfg: Config, api_base: str | None = None):
        self.cfg = cfg
        self.client = build_client()
        self.watchdog = Watchdog(fail_alert_after_s=cfg.yaml.fail_alert_after_s)
        self.filter = None
        if cfg.yaml.filter.enabled:
            self.filter = build_filter(
                cfg.yaml.filter.provider,
                cfg.settings.ANTHROPIC_API_KEY,
                cfg.yaml.filter.model,
                cfg.yaml.filter.criteria,
            )
        self.alerts_notifier = DiscordNotifier(
            self.client, cfg.settings.DISCORD_ALERTS_WEBHOOK_URL, username="ReleaseRadar"
        )
        self.health_notifier = DiscordNotifier(
            self.client, cfg.settings.DISCORD_HEALTH_WEBHOOK_URL, username="ReleaseRadar Health"
        )
        self.source = GithubReleasesSource(
            self.client,
            None,  # conn bound per-cycle
            token=cfg.settings.GITHUB_TOKEN,
            include_prereleases=cfg.yaml.sources.github_releases.include_prereleases,
            api_base=api_base or API,
        )
        self.stop = False

    # ------------------------------------------------------------------ loop
    def run_forever(self) -> None:
        log.info("scheduler_start", poll_interval_s=self.cfg.yaml.poll_interval_s)
        while not self.stop:
            started = time.time()
            try:
                self.run_once()
            except Exception as e:  # keep the loop alive
                log.error("cycle_exception", error=repr(e))
            elapsed = time.time() - started
            base = self.cfg.yaml.poll_interval_s
            sleep_s = max(0.5, base - elapsed) + random.uniform(0, self.cfg.yaml.jitter_s)
            time.sleep(sleep_s)

    # ----------------------------------------------------------------- cycle
    def run_once(self) -> dict:
        """Execute one poll cycle across all configured targets. Returns a small summary."""
        cycle_id = str(uuid.uuid4())
        targets = self.cfg.yaml.sources.github_releases.targets
        new_items: list[Item] = []
        detected: dict[str, datetime] = {}
        statuses: list[str] = []

        with db_session(self.cfg.db_path) as conn:
            self.source.conn = conn
            self.watchdog.load_json(get_kv(conn, "watchdog"))

            for target in targets:
                until = get_kv(conn, f"backoff_until:{target}")
                if until and time.time() < float(until):
                    log.info(
                        "check_skipped_backoff",
                        target=target,
                        wait_s=round(float(until) - time.time(), 1),
                    )
                    continue

                started_at = _now()
                try:
                    fr = self.source.fetch(target)
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"[:300]
                    self._record(conn, cycle_id, target, started_at, 0, "error", None, 0, None, err)
                    statuses.append("error")
                    self._handle_failure(conn, target, err)
                    continue

                statuses.append(fr.status)
                fresh: list[Item] = []
                if fr.status == "ok":
                    # First successful fetch of a target = baseline: mark seen, never alert.
                    baseline = not is_baselined(conn, target)
                    fresh = mark_new(conn, fr.items, baseline=baseline)
                    if baseline:
                        mark_baselined(conn, target)
                        record_health_event(
                            conn, "baseline", f"baselined {len(fr.items)} on {target}"
                        )
                    stamp = _now()
                    for it in fresh:
                        detected[it.key] = stamp
                    new_items.extend(fresh)
                    set_kv(conn, f"backoff_until:{target}", None)
                elif fr.status in ("rate_limited", "error") and fr.backoff_s:
                    set_kv(conn, f"backoff_until:{target}", str(time.time() + fr.backoff_s))

                self._record(
                    conn, cycle_id, target, started_at, fr.duration_ms, fr.status,
                    fr.http_status, len(fresh), fr.rate_remaining, fr.error,
                )
                if fr.status in ("error", "rate_limited"):
                    self._handle_failure(conn, target, fr.error or fr.status)

            if new_items:
                self._process_new(conn, new_items, detected)
            self._retry_pending(conn)

            failed = any(s in ("error", "rate_limited") for s in statuses)
            if not failed and statuses:
                self._handle_success(conn)
            set_kv(conn, "watchdog", self.watchdog.to_json())
            self._maybe_heartbeat(conn)

        return {"cycle_id": cycle_id, "statuses": statuses, "new": len(new_items)}

    def _record(
        self, conn, cycle_id, target, started_at, duration_ms, status, http_status,
        new_items, rate_remaining, error,
    ) -> None:
        record_check(
            conn,
            CheckResult(
                cycle_id=cycle_id, target=target, started_at=started_at,
                duration_ms=duration_ms, status=status, http_status=http_status,
                new_items=new_items, rate_remaining=rate_remaining, error=error,
            ),
        )
        # Every single check is logged (JSON line) in addition to the `checks` table row.
        log.info(
            "check", cycle_id=cycle_id, target=target, status=status, http_status=http_status,
            duration_ms=duration_ms, new_items=new_items, rate_remaining=rate_remaining,
            error=error,
        )

    # ------------------------------------------------------------- alerting
    def _process_new(self, conn, items: list[Item], detected: dict[str, datetime]) -> None:
        for it in items:
            decision = None
            if self.filter is not None:
                cached = get_filter_decision(conn, it.key)
                if cached is not None:
                    decision = cached
                else:
                    decision = self.filter.decide(it)
                    save_filter_decision(conn, decision)
            if decision is not None and not decision.keep:
                log.info("item_filtered_out", item_key=it.key, reason=decision.reason)
                continue
            self._alert(conn, it, decision, detected.get(it.key) or _now())

    def _alert(self, conn, item: Item, decision, detected_at: datetime) -> None:
        try:
            status = self.alerts_notifier.send_item(item, decision)
        except Exception as e:
            enqueue_pending(conn, item.key, item.model_dump_json())
            log.warning("alert_failed_queued", item_key=item.key, error=type(e).__name__)
            return
        self._store_alert(conn, item, status, detected_at)

    def _store_alert(self, conn, item: Item, status: int, detected_at: datetime) -> None:
        alerted_at = _now()
        latency = (alerted_at - item.published_at).total_seconds()
        inserted = insert_alert(
            conn,
            AlertRecord(
                item_key=item.key, channel="discord", published_at=item.published_at,
                detected_at=detected_at, alerted_at=alerted_at, latency_s=latency,
                http_status=status,
            ),
        )
        log.info(
            "alert_sent", item_key=item.key, latency_s=round(latency, 3),
            detect_to_alert_s=round((alerted_at - detected_at).total_seconds(), 3),
            duplicate_guard=not inserted,
        )

    def _retry_pending(self, conn) -> None:
        for row in list_pending(conn):
            try:
                item = Item.model_validate(json.loads(row["payload_json"]))
            except Exception:
                drop_pending(conn, row["item_key"])
                continue
            try:
                status = self.alerts_notifier.send_item(item, None)
            except Exception as e:
                bump_pending_attempt(conn, row["item_key"], type(e).__name__)
                continue
            self._store_alert(conn, item, status, _now())
            drop_pending(conn, item.key)
            log.info("pending_alert_recovered", item_key=item.key)

    # --------------------------------------------------------------- health
    def _safe_health_post(self, text: str) -> None:
        try:
            self.health_notifier.send_text(text)
        except Exception as e:
            log.warning("health_post_failed", error=type(e).__name__)

    def _handle_failure(self, conn, target: str, error: str) -> None:
        for _ev in self.watchdog.record_failure(error, target):
            mins = self.watchdog.fail_alert_after_s / 60
            record_health_event(conn, "failure_alert", f"{target}: {error}")
            self._safe_health_post(
                f"@here ReleaseRadar FAILING for {mins:.0f}+ min - last error: {error} "
                f"(target {target})."
            )

    def _handle_success(self, conn) -> None:
        for _ev in self.watchdog.record_success():
            mins = self.watchdog.last_outage_min
            record_health_event(conn, "recovery", f"after {mins:.1f} min")
            self._safe_health_post(f"ReleaseRadar recovered after {mins:.1f} min outage.")
        ok = ping_healthchecks(self.cfg.settings.HEALTHCHECKS_PING_URL, self.client)
        if not ok:
            record_health_event(conn, "hc_ping_fail", "ping failed")
        log.info("healthchecks_ping", ok=ok)

    def _maybe_heartbeat(self, conn) -> None:
        raw = get_kv(conn, "last_heartbeat")
        if raw is None:
            set_kv(conn, "last_heartbeat", _now().isoformat())
            return
        age = (_now() - datetime.fromisoformat(raw)).total_seconds()
        if age < self.cfg.yaml.heartbeat_interval_s:
            return
        msg = heartbeat_summary(conn, raw)
        record_health_event(conn, "heartbeat", msg)
        self._safe_health_post(msg)
        set_kv(conn, "last_heartbeat", _now().isoformat())

    def shutdown(self) -> None:
        self.stop = True
        self.client.close()
