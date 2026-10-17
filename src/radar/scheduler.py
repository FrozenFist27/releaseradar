"""The main scheduler loop: fetch -> dedupe -> filter -> alert -> health."""

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
    insert_alert,
    is_baselined,
    list_pending,
    mark_baselined,
    record_check,
    save_filter_decision,
)
from .dedupe import mark_new
from .filter.llm import build_filter
from .health import Watchdog, heartbeat_summary, ping_healthchecks, record_health_event
from .http import build_client
from .logging_setup import get_logger
from .models import AlertRecord, CheckResult, Item
from .notify.discord import DiscordNotifier
from .sources.github_releases import GithubReleasesSource

log = get_logger("radar.scheduler")


def _now() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = build_client()
        self.watchdog = Watchdog(fail_alert_after_s=cfg.yaml.fail_alert_after_s)
        self.last_heartbeat = _now()
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
        )
        self.stop = False

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

    def run_once(self) -> None:
        """Execute one poll cycle across all configured targets."""
        cycle_id = str(uuid.uuid4())
        targets = self.cfg.yaml.sources.github_releases.targets
        new_items: list[Item] = []

        with db_session(self.cfg.db_path) as conn:
            self.source.conn = conn
            for target in targets:
                started_at = _now()
                try:
                    fr = self.source.fetch(target)
                except Exception as e:
                    fr = None
                    record_check(
                        conn,
                        CheckResult(
                            cycle_id=cycle_id,
                            target=target,
                            started_at=started_at,
                            duration_ms=0,
                            status="error",
                            error=repr(e),
                        ),
                    )
                    self._handle_failure(conn, target, repr(e))
                    continue

                if fr.status == "ok":
                    # Baseline on the very first successful fetch for a target
                    # (even if it currently has zero items), then alert only on
                    # genuinely new stable IDs afterwards.
                    baseline = not is_baselined(conn, target)
                    fresh = mark_new(conn, fr.items, baseline=baseline)
                    if baseline:
                        mark_baselined(conn, target)
                    new_items.extend(fresh)
                    record_check(
                        conn,
                        CheckResult(
                            cycle_id=cycle_id,
                            target=target,
                            started_at=started_at,
                            duration_ms=fr.duration_ms,
                            status="ok",
                            http_status=fr.http_status,
                            new_items=len(fresh),
                            rate_remaining=fr.rate_remaining,
                        ),
                    )
                    if baseline:
                        record_health_event(conn, "baseline", f"baselined {len(fr.items)} on {target}")
                elif fr.status == "not_modified":
                    record_check(
                        conn,
                        CheckResult(
                            cycle_id=cycle_id,
                            target=target,
                            started_at=started_at,
                            duration_ms=fr.duration_ms,
                            status="not_modified",
                            http_status=304,
                            rate_remaining=fr.rate_remaining,
                        ),
                    )
                elif fr.status == "rate_limited":
                    record_check(
                        conn,
                        CheckResult(
                            cycle_id=cycle_id,
                            target=target,
                            started_at=started_at,
                            duration_ms=fr.duration_ms,
                            status="rate_limited",
                            http_status=fr.http_status,
                            rate_remaining=fr.rate_remaining,
                            error=fr.error,
                        ),
                    )
                else:  # error
                    record_check(
                        conn,
                        CheckResult(
                            cycle_id=cycle_id,
                            target=target,
                            started_at=started_at,
                            duration_ms=fr.duration_ms,
                            status="error",
                            http_status=fr.http_status,
                            error=fr.error,
                        ),
                    )
                    self._handle_failure(conn, target, fr.error or "error")

            # Filter + alert new items
            if new_items:
                self._process_new(conn, new_items)

            # Retry any pending alerts
            self._retry_pending(conn)

            # Health: success path
            any_error = any(
                r["status"] == "error"
                for r in conn.execute(
                    "SELECT status FROM checks WHERE cycle_id=?", (cycle_id,)
                ).fetchall()
            )
            if not any_error:
                self._handle_success(conn)
            self._maybe_heartbeat(conn)

    def _process_new(self, conn, items: list[Item]) -> None:
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
            self._alert(conn, it, decision)

    def _alert(self, conn, item: Item, decision) -> None:
        try:
            status = self.alerts_notifier.send_item(item, decision)
            alerted_at = _now()
            latency = (alerted_at - item.published_at).total_seconds()
            inserted = insert_alert(
                conn,
                AlertRecord(
                    item_key=item.key,
                    channel="discord",
                    published_at=item.published_at,
                    detected_at=alerted_at,
                    alerted_at=alerted_at,
                    latency_s=latency,
                    http_status=status,
                ),
            )
            log.info(
                "alert_sent",
                item_key=item.key,
                latency_s=round(latency, 3),
                duplicate_guard=not inserted,
            )
        except Exception as e:
            enqueue_pending(conn, item.key, item.model_dump_json())
            log.warning("alert_failed_queued", item_key=item.key, error=repr(e))

    def _retry_pending(self, conn) -> None:
        for row in list_pending(conn):
            try:
                item = Item.model_validate(json.loads(row["payload_json"]))
            except Exception:
                drop_pending(conn, row["item_key"])
                continue
            try:
                status = self.alerts_notifier.send_item(item, None)
                alerted_at = _now()
                latency = (alerted_at - item.published_at).total_seconds()
                insert_alert(
                    conn,
                    AlertRecord(
                        item_key=item.key,
                        channel="discord",
                        published_at=item.published_at,
                        detected_at=alerted_at,
                        alerted_at=alerted_at,
                        latency_s=latency,
                        http_status=status,
                    ),
                )
                drop_pending(conn, item.key)
                log.info("pending_alert_recovered", item_key=item.key)
            except Exception as e:
                bump_pending_attempt(conn, row["item_key"], repr(e))

    def _handle_failure(self, conn, target: str, error: str) -> None:
        events = self.watchdog.record_failure(error, target)
        for ev in events:
            record_health_event(conn, "failure_alert", ev)
            mins = self.watchdog.fail_alert_after_s / 60
            try:
                self.health_notifier.send_text(
                    f"@here ReleaseRadar FAILING for {mins:.0f} min — last error: {error} (target {target})."
                )
            except Exception:
                pass

    def _handle_success(self, conn) -> None:
        events = self.watchdog.record_success()
        for _ in events:
            record_health_event(conn, "recovery", "recovered")
            try:
                mins = self.watchdog.rearm_interval_s / 60
                self.health_notifier.send_text(f"ReleaseRadar recovered after {mins:.0f} min outage.")
            except Exception:
                pass
        ok = ping_healthchecks(self.cfg.settings.HEALTHCHECKS_PING_URL, self.client)
        if not ok:
            record_health_event(conn, "hc_ping_fail", "healthchecks ping failed")
        else:
            record_health_event(conn, "hc_ping", "ok")

    def _maybe_heartbeat(self, conn) -> None:
        if (_now() - self.last_heartbeat).total_seconds() < self.cfg.yaml.heartbeat_interval_s:
            return
        since = self.last_heartbeat.isoformat()
        msg = heartbeat_summary(conn, since)
        record_health_event(conn, "heartbeat", msg)
        try:
            self.health_notifier.send_text(msg)
        except Exception:
            pass
        self.last_heartbeat = _now()

    def shutdown(self) -> None:
        self.stop = True
        self.client.close()
