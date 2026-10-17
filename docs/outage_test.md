# Outage tests (recorded 2026-10-17, UTC)

## A. Watchdog drill (`radar simulate-outage --minutes 6`)

Real checks against an unreachable API (`127.0.0.1:9`) with a throw-away DB, a 30 s interval and the
real health webhook. Healthchecks pings were disabled for the drill.

| Time | Event |
|---|---|
| 16:45:29.995 | outage start |
| 16:50:45.929 | LOUD `@here` alert posted to the health webhook (316 s after first failure; threshold 300 s) |
| 16:51:58.991 | real API restored; recovery message ("after 6.4 min") posted |

Exactly one loud alert was fired (no repeats within the 30 min re-arm window).

## B. Dead-man switch (VM timer stopped)

Healthchecks.io check "releaseradar": period 1 min, grace 5 min, integrations email + Discord.

| Time | Event |
|---|---|
| 16:45:15 | last ping from the VM |
| 16:45:23 | `systemctl stop radar-check.timer` on the VM |
| 16:51 | Healthchecks event log: status *up -> down* (about 6 min after the last ping) |
| 16:51 | ping #40 from a browser User-Agent on the owner's IP (not ReleaseRadar) set it back to *up* |
| 16:53:39 | `systemctl start radar-check.timer`; pings from 35.209.159.81 resumed |

Gap in the `checks` table: 507 s (the only gap > 120 s). Not verified from the VM: whether the
Discord/email notification arrived (Healthchecks log shows the state change only).
