# Deploying ReleaseRadar to a GCP e2-micro Always-Free VM

Target: project `upwork-sambudh`, instance `releaseradar`, zone `us-central1-a`,
Debian 12, Python 3.11, 969 MB RAM. Stays inside the free tier (e2-micro in
us-central1, 30 GB pd-standard, ephemeral IP, no static IP, no extra disks).

On Windows set the SDK's bundled Python first:

```bash
export CLOUDSDK_PYTHON="C:/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/platform/bundledpython/python.exe"
G="gcloud compute --project=upwork-sambudh"
```

## Design: systemd service + timer

* `radar-check.service` (oneshot) runs `radar once` = one full poll cycle, then exits.
* `radar-check.timer` fires it every 30 s (`OnUnitActiveSec=30s`).
* All cross-cycle state (ETags, seen-set, watchdog, heartbeat clock, backoff) lives in
  SQLite, so one-shot processes behave exactly like a long-running loop.
* `radar-publisher.timer` (optional) publishes a synthetic release in the sandbox repo every
  ~2 h; this is the latency harness.
* Stopping `radar-check.timer` is the outage drill: pings stop, Healthchecks.io alerts.

## 1. Package, copy code and secrets

```bash
tar czf /tmp/radar-src.tgz --exclude=__pycache__ --exclude='*.egg-info' \
  src pyproject.toml README.md config.yaml deploy scripts
$G scp --zone=us-central1-a --quiet /tmp/radar-src.tgz deploy/vm-setup.sh .env releaseradar:/tmp/
# secrets: local .env -> /etc/releaseradar.env (root, chmod 600). Never echo values.
$G ssh releaseradar --zone=us-central1-a --quiet --command="
  sudo mv /tmp/.env /etc/releaseradar.env &&
  sudo chown root:root /etc/releaseradar.env && sudo chmod 600 /etc/releaseradar.env"
```

## 2. One-time VM setup (1 GB swapfile, radar user, venv under /opt/releaseradar)

```bash
$G ssh releaseradar --zone=us-central1-a --quiet --command="bash /tmp/vm-setup.sh"
```

`deploy/vm-setup.sh` is idempotent enough to re-run for upgrades (it re-extracts the
tarball and `pip install`s into the venv).

## 3. Enable the timers

```bash
$G ssh releaseradar --zone=us-central1-a --quiet --command="
  sudo cp /opt/releaseradar/deploy/radar-*.service /opt/releaseradar/deploy/radar-*.timer /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl start radar-check.service &&          # first run baselines existing releases
  sudo systemctl enable --now radar-check.timer radar-publisher.timer"
```

## 4. Verify / read logs

```bash
$G ssh releaseradar --zone=us-central1-a --quiet --command="
  systemctl list-timers --no-pager | grep radar;
  sudo journalctl -u radar-check -n 20 --no-pager"
```

Every check is a JSON line (`"event": "check"`) in the journal and in
`/opt/releaseradar/data/logs/radar-<date>.jsonl`, and a row in the `checks` table.

## 5. Outage drill

```bash
$G ssh releaseradar ... --command="sudo systemctl stop radar-check.timer"   # note the time
# Healthchecks.io (period 1 min + grace 5 min) marks the check DOWN ~6 min after the last ping
$G ssh releaseradar ... --command="sudo systemctl start radar-check.timer"
```

## Free-tier checklist

- Region `us-central1-a`, machine `e2-micro`, 30 GB `pd-standard` boot disk.
- No static IP, no extra disks, no load balancer, no Cloud NAT.
- Egress is a few MB/day (JSON polls + Discord posts).
