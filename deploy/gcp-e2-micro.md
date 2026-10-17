# Deploying ReleaseRadar to a GCP e2-micro Always-Free VM

Target: project `upwork-sambudh`, instance `releaseradar`, zone `us-central1-a`,
Debian 12, Python 3.11, 969 MB RAM. Stays inside the free tier (e2-micro in
us-central1, 30 GB pd-standard, standard network tier, no static IP).

On this Windows machine set the SDK's bundled Python first:

```bash
export CLOUDSDK_PYTHON="C:/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/platform/bundledpython/python.exe"
```

## 1. One-time VM prep (swap + dirs)

```bash
gcloud compute ssh releaseradar --zone=us-central1-a --quiet --command="
  set -e
  # 1 GB swapfile (the box has only 969 MB RAM)
  sudo fallocate -l 1G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  sudo useradd --system --shell /usr/sbin/nologin radar || true
  sudo mkdir -p /opt/releaseradar /etc/releaseradar.env.d
  sudo chown -R radar: /opt/releaseradar
  python3 --version
"
```

## 2. Copy the code and secrets

From the project root on your machine:

```bash
# code ( excludes .env, data/, venv )
gcloud compute scp --recurse --zone=us-central1-a --quiet \
  src pyproject.toml config.yaml deploy \
  releaseradar:~/releaseradar-src/

# secrets: local .env -> /etc/releaseradar.env (chmod 600). Never echo values.
gcloud compute scp --zone=us-central1-a --quiet .env releaseradar:/tmp/radar.env
gcloud compute ssh releaseradar --zone=us-central1-a --quiet --command="
  sudo mv /tmp/radar.env /etc/releaseradar.env
  sudo chmod 600 /etc/releaseradar.env
  sudo chown root:root /etc/releaseradar.env
"
```

## 3. Install into /opt with a venv

```bash
gcloud compute ssh releaseradar --zone=us-central1-a --quiet --command="
  set -e
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-pip >/dev/null
  cd /opt/releaseradar
  sudo rsync -a ~/releaseradar-src/ /opt/releaseradar/
  sudo python3 -m venv /opt/releaseradar/.venv
  sudo /opt/releaseradar/.venv/bin/pip install --quiet --upgrade pip
  sudo /opt/releaseradar/.venv/bin/pip install --quiet .
  sudo chown -R radar: /opt/releaseradar
"
```

## 4. systemd service + timer

ReleaseRadar is a long-running loop, so a **service** with `Restart=always` is
the right unit. (A timer is used only for the optional latency-harness publisher.)

```bash
gcloud compute ssh releaseradar --zone=us-central1-a --quiet --command="
  set -e
  sudo cp /opt/releaseradar/deploy/radar.service /etc/systemd/system/radar.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now radar
  sleep 3
  systemctl is-active radar
  sudo journalctl -u radar -n 20 --no-pager
"
```

## 5. Verify

```bash
gcloud compute ssh releaseradar --zone=us-central1-a --quiet --command="
  sudo journalctl -u radar -f -n 0
"
```

You should see JSON log lines (`scheduler_start`, per-target HTTP 200/304) and a
Healthchecks.io ping every cycle. Logs also land in `/opt/releaseradar/data/logs/radar-<date>.jsonl`.

## Staying in the free tier

- Region `us-central1-a` (us-central1 is Always-Free eligible).
- Machine type `e2-micro` (shared core, 1 GB RAM) — free per month.
- 30 GB `pd-standard` boot disk — free per month.
- No static external IP assigned beyond the ephemeral one (ephemeral is free).
- No extra disks, no GPUs, no load balancers.
