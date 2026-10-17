# ReleaseRadar — running cost

All infrastructure fits inside free tiers. The only variable cost is the optional
LLM filter, which is off by default.

| Item | Expected | Measured |
|---|---|---|
| GCP e2-micro Always-Free VM + 30 GB pd-standard (us-central1) | $0 within free tier | $0 (free-tier instance, ephemeral IP) |
| GitHub REST API | $0 | $0 (authenticated; 304s don't count against primary limit) |
| Discord webhooks | $0 | $0 |
| Healthchecks.io (free plan) | $0 | $0 |
| LLM filter (claude-haiku-5-5) | items × tokens × $0.10/MTok in + $0.50/MTok out | ~165 in + ~80 out tokens/item ≈ $0.00006/item |

## Measured LLM spend (single 3-item filter eval, real API calls)

- Input tokens: 494 total (171 + 158 + 165)
- Output tokens: 241 total (84 + 74 + 83)
- Cost: (494 × $0.10 + 241 × $0.50) / 1,000,000 = **$0.00017** for 3 items
- i.e. **~$0.000057 per filtered item**

## Extrapolation

At a generous 50 new releases/day filtered for a month (1,500 items):

- LLM tokens ≈ 1,500 × (165 in + 80 out) = 247,500 in + 120,000 out
- Cost ≈ (247,500 × $0.10 + 120,000 × $0.50) / 1e6 = **$0.084 / month**

So even a busy month of AI filtering costs under a dime; with the filter off, the
whole system runs at **$0 / month** within free tiers.
