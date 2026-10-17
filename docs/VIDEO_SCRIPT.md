# ReleaseRadar - 2-minute demo video script

Total <= 2:00. Screen-record a terminal and Discord side by side. Numbers come from `docs/results.md`
(13 sandbox releases, 26-minute window; replace with the 7-day figures once the run ends).

| Time | Shot | Narration |
|---|---|---|
| 0:00-0:12 | Title card + Discord alerts channel with a release embed | "ReleaseRadar tells you within a minute when something new ships - and never twice." |
| 0:12-0:30 | `config.yaml`, then `journalctl -u radar-check -f` showing one JSON `check` line per repo | "It polls official GitHub APIs every 30 seconds with ETags and logs every single check." |
| 0:30-0:55 | `python scripts/publish_test_releases.py --now` with a stopwatch, Discord embed appears | "I publish a release in my sandbox repo... the alert lands [N] seconds later - measured p50 16 s, worst 28 s." |
| 0:55-1:10 | `systemctl restart`/next timer run, then `radar report` showing duplicates = 0 | "Every poll is a fresh process; state is in SQLite, so restarts and reordered lists can't cause a duplicate." |
| 1:10-1:25 | `radar simulate-outage` -> `@here` message in the health channel | "If checks fail for five minutes, you get a loud alert - then a recovery message." |
| 1:25-1:45 | `systemctl stop radar-check.timer`, Healthchecks.io dashboard going red ~6 min later (time-lapse) | "If the box itself dies, an external dead-man switch tells you." |
| 1:45-2:00 | `radar report` table + README results | "Seven days unattended on a free-tier VM: [final numbers]. Link below." |

Optional shot only if a valid Anthropic key is configured: LLM filter keeping one item with a summary and
skipping another. (Not measured yet - skip this shot otherwise.)

## Recording checklist

- [ ] Real Discord alert embed (tag, author, link, footer with item key).
- [ ] JSON `check` log lines from the VM journal.
- [ ] Publish -> alert with visible stopwatch.
- [ ] `radar report` with 0 duplicates.
- [ ] Loud `@here` message and recovery message.
- [ ] Healthchecks.io up -> down transition.
