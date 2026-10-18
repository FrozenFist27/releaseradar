# Upwork portfolio entry

> All figures come
> from real runs on public/synthetic data; the 7-day figures are pending (run started 2026-10-17T16:42Z).

**Title:** ReleaseRadar - Monitor & Alert Bot with Zero-Duplicate Alerts

**Description:**

A small, production-style monitor that watches public sources (GitHub releases) and posts
only genuinely new items to Discord within a minute. Items are tracked by stable ID in SQLite, so
reordered, edited or re-shared entries never alert twice. A health layer posts heartbeats, raises a loud
`@here` alert if checks fail for 5+ minutes, and an external dead-man switch (Healthchecks.io) alerts if the
host dies. Runs as a systemd timer on a free-tier GCP VM. An optional Claude Haiku filter is implemented
(unit-tested; live evaluation pending a valid API key).

Measured so far (VM, 26-minute window, 2026-10-17):
- 148 checks, 0 errors; 13 sandbox releases alerted exactly once each (0 duplicates, audited from the DB and the journal)
- Publish-to-alert latency: p50 16.4 s, p95 27.5 s, max 27.6 s (30 s polling)
- Simulated outage -> loud alert after 316 s; VM stopped -> Healthchecks.io down after ~6 min
- Running cost: $0 infrastructure; optional AI filter measured at ~$0.000085 per item (30-item eval: 100% accuracy in one run, 96.7% in another)
- 7-day unattended result: `[PENDING - fill from docs/results.md after 2026-10-24]`

Stack: Python 3.11, httpx, SQLite, Discord webhooks, Healthchecks.io, systemd timers, Docker, GCP free tier.

**Skills tags:** Python, API Integration, Automation, Monitoring, Web Scraping, Discord Bot, SQLite, Docker, LLM.

**Media to attach:** demo video (<=2 min, docs/VIDEO_SCRIPT.md), architecture diagram, Discord alert
screenshot, results table.

## What this demonstrates to a client

- Official APIs + conditional requests (polite, rate-limit-aware) rather than brittle HTML scraping.
- Database-enforced exactly-once alerting (stable-ID dedupe + PRIMARY KEY guard) with an independent log audit.
- Restart-safe state; every poll is a fresh process and nothing is lost or repeated.
- Two-layer observability: internal watchdog + external dead-man switch, both drilled for real.
- Honest reporting: pending items are labelled as pending.

**Links:** GitHub repo https://github.com/FrozenFist27/releaseradar · demo video: to be recorded (script in `docs/VIDEO_SCRIPT.md`).
