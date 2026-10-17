# Upwork portfolio entry (label: DEMO PROJECT)

> This is a demo project built to showcase a repeatable skill. It is not a live
> client engagement. All figures come from a real measured run on public/synthetic data.

**Title:** ReleaseRadar — Monitor & Alert Bot with Zero-Duplicate Alerts (Demo Project)

**Description:**

Demo project. A small, production-style monitor that watches public sources (GitHub
releases; optionally UK public tender notices) and posts only genuinely new items to
Discord or Slack within a minute. Items are tracked by stable ID, so reordered, edited
or re-shared entries never alert twice. An optional AI filter (Claude Haiku) screens
items against plain-English criteria and adds a one-line summary. A two-layer health
system posts heartbeats, raises a loud alert if checks fail for 5+ minutes, and an
external dead-man switch (Healthchecks.io) alerts if the host dies.

Measured (real run, public/synthetic data only):
- Publish-to-alert latency: p50 ~8.4 s, p95 ~9.3 s, max 9.4 s (n=5 sandbox releases)
- Sampled window: 40 checks, 100% success, 0 duplicate alerts
- AI filter: correct keep/skip on a 3-case set; ~165 input + ~80 output tokens per item
- Running cost: $0 infra (GCP Always-Free e2-micro + GitHub + Discord + Healthchecks.io free tier) + a fraction of a cent of LLM tokens per item

Stack: Python 3.11/3.12, httpx, SQLite, Discord webhooks, Healthchecks.io, Anthropic
claude-haiku-5-5 (optional filter), Docker, systemd, GCP free tier.

**Skills tags:** Python, API Integration, Automation, Monitoring, Web Scraping, Discord Bot, Slack, LLM, SQLite, Docker.

**Media to attach:** demo video (<=2 min, see docs/VIDEO_SCRIPT.md), architecture diagram, Discord alert screenshot, results table.

## What this demonstrates to a client

- Official APIs + conditional requests (polite, rate-limit-aware polling) — not brittle HTML scraping.
- Database-enforced exactly-once alerting (stable-ID dedupe + PRIMARY KEY guard).
- Restart-safe state, at-least-once delivery with a pending queue.
- Two-layer observability: internal watchdog + external dead-man switch.
- Optional LLM filtering that fails open, with token/cost accounting.
- Real measured numbers, not marketing claims.
