#!/usr/bin/env python3
"""Latency harness: publish a synthetic release in the sandbox repo.

Usage:
    python scripts/publish_test_releases.py --now            # publish one immediately
    python scripts/publish_test_releases.py --loop --hours 7 # every 2h for 7h

Reads SANDBOX_REPO / SANDBOX_GITHUB_TOKEN from the environment (.env).
Writes no secrets to disk. Tag format: vYYYYMMDD-HHMMSS.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running from the repo root without install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402

from radar.scripts_publish import publish_release  # noqa: E402


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="Publish one release immediately")
    ap.add_argument("--loop", action="store_true", help="Publish on a schedule")
    ap.add_argument("--hours", type=float, default=7.0, help="How long the loop runs")
    ap.add_argument("--interval-min", type=float, default=120, help="Minutes between releases")
    ap.add_argument("--tag", type=str, default=None)
    args = ap.parse_args()

    load_dotenv()
    repo = os.environ.get("SANDBOX_REPO", "")
    token = os.environ.get("SANDBOX_GITHUB_TOKEN", "")
    if not repo or not token:
        print("SANDBOX_REPO / SANDBOX_GITHUB_TOKEN not set", file=sys.stderr)
        return 1

    def one() -> None:
        tag = args.tag or "v" + time.strftime("%Y%m%d-%H%M%S")
        with httpx.Client(timeout=30) as c:
            rel = publish_release(c, repo, token, tag)
        print(f"published tag={tag} id={rel.get('id')} published_at={rel.get('published_at')}")

    if args.now or not args.loop:
        one()
        return 0

    deadline = time.time() + args.hours * 3600
    while time.time() < deadline:
        try:
            one()
        except Exception as e:
            print(f"publish failed: {e}", file=sys.stderr)
        time.sleep(args.interval_min * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
