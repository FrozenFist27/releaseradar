# ReleaseRadar

> **Know the minute something new ships — never the same alert twice.**

[![tests](https://img.shields.io/badge/tests-43%20passed-brightgreen)](#tests)
[![licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![demo](https://img.shields.io/badge/demo-project-lightgrey)](docs/UPWORK_ENTRY.md)

ReleaseRadar is a small, production-style **monitor-and-alert** service. It watches
public APIs (GitHub Releases; optionally UK Contracts Finder tender notices) and posts
**only genuinely new items** to Discord within a minute. Items are tracked
by **stable ID** in SQLite, so a reordered list, an edited release, or a service restart
can never produce a duplicate alert. An **optional AI filter** (Claude Haiku) screens
items against plain-English criteria, and a **two-layer health system** (internal
watchdog + external Healthchecks.io dead-man switch) tells you if the monitor itself
stops.

Every number below comes from a real run against
public/synthetic data (see [Results](#results-measured)).

---

## Problem

- Important updates — dependency releases, public tenders, changelogs — appear without
  warning. Checking by hand wastes hours.
- Naive scrapers alert on **page position**, so a reordered or boosted item spams
  duplicates.
- Monitors fail **silently**; you only find out after you've already missed something.

## Approach

- Poll **official APIs** politely: conditional requests (`If-None-Match` / ETag), so
  unchanged feeds cost almost nothing and don't count against the primary rate limit.
- Detect by **stable ID** (the GitHub release's numeric `id`), never by list position or
  title. Seen once → never alerted again, enforced by the database.
- **Optional AI filter**: each new item is screened against your criteria and summarised;
  decisions are cached per item and the filter **fails open** so nothing is silently lost.
- **Alert + watch itself**: rich Discord embeds, heartbeats, a loud `@here` alarm if
  checks fail for 5+ minutes, and an external dead-man switch for host death.

## Architecture

```
 config.yaml ─┐                                              ┌──> Discord #radar-alerts
 .env ────────┼─> Scheduler loop (30s ± jitter) ─────────────┤
              │        │                                     └──> Discord #radar-health
              │        v                                          ^        ^
              │  GitHubReleasesSource (httpx + ETag + rate guard)  │        │
              │        │  GET /repos/{o}/{r}/releases              │        │
              │        v                                           │        │
              │  Normalizer -> Item(source, item_id, ...)          │        │
              │        │                                          │        │
              │        v                                          │        │
              │  Dedupe (SQLite seen_items, PK = source:item_id)   │        │
              │        │  new items only                          │        │
              │        v                                          │        │
              │  [optional] LLM filter (claude-haiku-5-5)          │        │
              │        │                                          │        │
              │        v                                          │        │
              │  DiscordNotifier -> alerts (latency recorded)      │        │
              │                                                   │        │
              └─> Health: Watchdog + heartbeat + Healthchecks.io ──┘        │
                                                                           │
                        Healthchecks.io dead-man switch ───────────────────┘
                        (alerts you if pings stop)
```

**Components** (`src/radar/`): `config` (env+YAML), `models`, `db` (SQLite), `http`
(ETag + rate-limit), `sources/github_releases`, `dedupe`, `filter/llm` (optional),
`notify/discord`, `health` (watchdog/ping), `scheduler`, `report`, `cli`.

## Results (measured)

Real numbers from the VM deployment (GCP e2-micro, `us-central1-a`), pulled with
`radar report` into `docs/results.md` / `docs/results.json`. Report generated
2026-10-17T17:08:56Z, i.e. **26.5 minutes into the run**. The 7-day figures are not in yet.

| Metric | Value (26.5 min window) |
|---|---|
| Checks logged | 148 (37 full poll cycles x 4 repos), 148 successful, 0 errors |
| Max gap between cycles | 507 s - the planned outage drill below (no other gap > 120 s) |
| Duplicate alerts | **0** - checked two ways: `alerts.item_key` PRIMARY KEY, and an independent count of `alert_sent` lines per item in the systemd journal (13 items, each posted exactly once) |
| Publish-to-alert latency (n = 13 sandbox releases) | p50 **16.4 s**, p95 **27.5 s**, max **27.6 s**, min 3.1 s (`alerted_at - GitHub published_at`) |
| Simulated outage -> loud alert | `@here` alert posted **316 s** after the first failing check (5-min threshold, 30 s check interval); recovery message after 6.4 min |
| VM stopped -> external alert | Healthchecks.io flipped *up -> down* at 16:51 UTC, ~6 min after the last ping at 16:45:15 (period 1 min + grace 5 min) |
| Monthly running cost | **$0** infrastructure (free tier); LLM filter off in the VM run; eval spend **$0.005** for 60 calls (see below) |

### 7-day unattended run

* **Started: 2026-10-17T16:42:39Z** (timer enabled on the VM). Planned end: 2026-10-24T16:42Z.
* The sandbox latency harness publishes a release about every 2 h (84 expected over the week).
* **Not finished at the time of writing.** To produce the final numbers, run on the VM:
  `sudo -u radar RADAR_DB_PATH=/opt/releaseradar/data/radar.db /opt/releaseradar/.venv/bin/radar report --log-dir /opt/releaseradar/data/logs`
  and replace `docs/results.*`. Expected checks: 7 d x 2,880 cycles/day x 4 repos = 80,640
  minus the planned outage.

### Outage test (recorded)

Details in [docs/outage_test.md](docs/outage_test.md).

1. Watchdog drill (`radar simulate-outage --minutes 6`): real failing checks against an unreachable
   API; loud `@here` message to the health webhook at +316 s; recovery message when the API returned.
2. Dead-man switch: `radar-check.timer` stopped on the VM at 16:45:23 UTC (last ping 16:45:15);
   Healthchecks.io logged *up -> down* at 16:51. Timer restarted 16:53:39 UTC.
   Whether the Discord/email notification was **delivered** was not verified from here
   (Healthchecks shows the status change, not delivery) - check your Discord health channel.
   A stray browser `GET` of the ping URL from the owner's IP at 16:51 flipped the check back to *up*
   (event #40); it did not come from ReleaseRadar.

### LLM filter (measured)

Live run of `scripts/eval_filter.py` against the 30 hand-labelled synthetic release notes
(`tests/fixtures/filter_eval.jsonl`), model `claude-haiku-5-5`, `max_tokens=200`, criteria "security fixes,
breaking changes or new major features". Two runs, both executed 2026-10-18:

| Run | Accuracy | False negatives | False positives | Fail-open errors | Input tok | Output tok | Cost |
|---|---|---|---|---|---|---|---|
| 1 | 96.7% (29/30) | 0 | 1 | 1 (counted as keep) | 7,664 | 3,431 | $0.0025 |
| 2 (`docs/filter_eval.json`) | 100% (30/30) | 0 | 0 | 0 | 7,664 | 3,578 | $0.0026 |

That is about 255 input / 119 output tokens and **$0.000085 per item**. Results vary slightly between runs
(model output is not deterministic); the 1 miss in run 1 was a fail-open (kept, never dropped). Only 30 small
synthetic items, so treat accuracy as indicative. Prompt-cache hit rate was not measured. The filter is
**off** in the 7-day VM run, so the VM run spent $0 on LLM.

## Cost per run / per month

See [docs/cost.md](docs/cost.md). Infrastructure is **$0** inside free tiers (GCP e2-micro +
30 GB pd-standard, ephemeral IP; GitHub API; Discord webhooks; Healthchecks.io free plan).
The only variable cost is the optional AI filter: measured **about $0.000085 per item** (255 in / 119 out tokens,
list price $0.10 / $0.50 per MTok), i.e. ~$0.0026 per 30-item eval run; the VM run has the filter off ($0).
One poll cycle (4 repos) takes ~2-5 s wall time and costs nothing.

## Tests

```bash
pytest          # 43 unit tests, no network (respx + freezegun + mocks)
ruff check src tests scripts
```

Covered: dedupe (same/reorder/add/restart/baseline), GitHub source parsing + ETag/304 + 429
back-off, rate-limit helpers, Discord notifier (payload, 429 retry, pending queue, PK guard),
watchdog thresholds + persistence across separate processes + recovery, heartbeat clock, LLM filter
parsing/fail-open/injection, JSONL logging, scheduler baseline->alert, report percentiles, cycle gaps
and the log-based duplicate audit.

## Limitations

- **Polling, not push.** Latency is bounded by the 30 s timer interval (measured max 27.6 s over 13 releases); GitHub
  webhooks would need repo-admin rights we don't have on third-party repos.
- GitHub `published_at` has 1-second precision.
- Discord rate limits (~30 msgs/min per webhook) — the notifier backs off on 429.
- The free-tier VM can be rebooted; the systemd timer resumes on boot and SQLite state makes
  it restart-safe. A 969 MB box needs the 1 GB swapfile for `pip install`.
- Only 13 latency samples and a 26-minute window so far; the 7-day numbers are pending.
- The sandbox repo accumulates ~84 harness releases over the week; the weekly cleanup is not implemented (delete manually).
- Healthchecks.io detects a dead box only after period + grace (~6 min).
- The LLM filter was evaluated on only 30 synthetic items, and not enabled in the 7-day VM run.
- The optional LLM filter can be wrong; it **fails open** (alerts rather than drops) and
  caches per item.
- A deleted-then-recreated release gets a new ID and therefore alerts (documented).

## Responsible use

Only sources whose terms allow automated access. No login walls, paywall bypass, or
anti-bot defeat. Official APIs with conditional requests and rate-limit backoff.

## Licence

MIT — see [LICENSE](LICENSE).
