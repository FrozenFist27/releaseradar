# ReleaseRadar - running cost

Infrastructure fits inside free tiers. The only variable cost is the optional LLM filter, which
is off by default.

| Item | Expected | Measured |
|---|---|---|
| GCP e2-micro (us-central1-a) + 30 GB pd-standard, ephemeral IP, 1 GB swapfile on the boot disk | $0 (Always Free) | $0 - no static IP, no extra disk created. Disk used: 2.1 GB of 30 GB |
| GitHub REST API | $0 | $0. Authenticated 5,000 req/h; 4 repos x 2,880 cycles/day = 11,520 requests/day, most of them 304 (not counted against the primary limit). Observed `X-RateLimit-Remaining` stayed above 4,900 |
| Discord webhooks | $0 | $0 |
| Healthchecks.io free plan | $0 | $0 |
| LLM filter (`claude-haiku-5-5`, $0.10 / $0.50 per MTok in/out, <100K context) | items x tokens x price | **$0.00 measured** - filter disabled in the run; the live eval could not run because the API key was rejected (HTTP 401, expired). Per-item token cost: `[NOT MEASURED]` |

## Cost per run

One poll cycle = 4 HTTPS GETs (~0.3-0.9 s each, 304 mostly) + one Healthchecks ping: no billable
component. Per alert: one Discord POST.

## Monthly

$0 on the free tier, plus Anthropic usage: measured $0.00 (not used). When the filter is enabled the
cost is `items_per_month x (input_tokens x $0.10 + output_tokens x $0.50) / 1e6`; with the system
prompt cached and `max_tokens=200` this is expected to be a small fraction of a cent per item, but that has
to be confirmed with `scripts/eval_filter.py` once a valid key is configured.
