# ReleaseRadar — 2-minute demo video script

Total run time: <= 2:00. Screen-record a terminal + Discord side by side where possible.
All latency figures below come from the real measured run (p50 8.4 s, p95 9.3 s).

| Time | Shot | Narration |
|---|---|---|
| 0:00–0:12 | Title card + Discord #radar-alerts with a release alert | "ReleaseRadar alerts you within a minute of something new — and never twice." |
| 0:12–0:30 | `config.yaml` + `radar run` JSON logs scrolling | "Point it at public GitHub repos or tender feeds. It polls politely with ETags, respects rate limits, and logs every check." |
| 0:30–0:55 | Terminal: `python scripts/publish_test_releases.py --now` -> stopwatch -> Discord alert appears | "I publish a release in my sandbox repo… and here's the Discord alert, [N] seconds later." (N = measured latency, ~8 s) |
| 0:55–1:10 | Re-run against reordered fixture / restart the service; no new alert | "Restart, reordered list, edited release — the stable ID means no duplicate." |
| 1:10–1:25 | LLM filter: one kept with a summary, one skipped with a reason | "The optional AI filter keeps only what matches your criteria and summarises it — and fails open so nothing is silently lost." |
| 1:25–1:45 | `radar simulate-outage` -> loud @here alert; stop the service -> Healthchecks.io alert | "If checks fail for 5 minutes, or the box dies, you hear about it from an external dead-man switch." |
| 1:45–2:00 | `radar report` output + README results table | "Seven days unattended: 100% uptime on the sample window, zero duplicates, ~8 s alerts. Repo link below." |

## Recording checklist

- [ ] Discord alerts channel showing a real ReleaseRadar embed (tag, author, link, latency footer).
- [ ] `radar run` producing JSON log lines (scheduler_start, alert_sent with latency_s).
- [ ] `publish_test_releases.py --now` followed by the alert appearing.
- [ ] A restart producing no duplicate alert.
- [ ] The optional LLM filter keeping one item and skipping another.
- [ ] `radar simulate-outage` loud alert + Healthchecks.io alert.
- [ ] `radar report` table + README results section.
