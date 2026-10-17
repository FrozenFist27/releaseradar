"""Typer CLI: run, once, report, init-db, simulate-outage, publish-test-release."""

from __future__ import annotations

import signal
import sys
import time

import typer

from .config import load_config
from .db import connect, db_session
from .health import record_health_event
from .logging_setup import setup_logging
from .report import compute_report, to_markdown, write_report

app = typer.Typer(help="ReleaseRadar — monitor-and-alert with zero duplicates.", no_args_is_help=True)


@app.command()
def init_db(config: str = typer.Option(None, help="Path to config.yaml")):
    """Create the SQLite schema."""
    cfg = load_config(config)
    connect(cfg.db_path)
    typer.echo(f"Initialized DB at {cfg.db_path}")


@app.command()
def once(config: str = typer.Option(None)):
    """Run a single poll cycle then exit."""
    cfg = load_config(config)
    setup_logging()
    from .scheduler import Scheduler

    s = Scheduler(cfg)
    s.run_once()
    s.shutdown()


@app.command()
def run(config: str = typer.Option(None)):
    """Run the poll loop until interrupted (SIGTERM/SIGINT graceful)."""
    cfg = load_config(config)
    setup_logging()
    from .scheduler import Scheduler

    s = Scheduler(cfg)

    def _graceful(signum, frame):
        typer.echo("Shutting down...")
        s.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    with db_session(cfg.db_path) as conn:
        record_health_event(conn, "startup", "scheduler starting")
    s.run_forever()


@app.command()
def report(
    config: str = typer.Option(None),
    out: str = typer.Option("docs", help="Output directory"),
    as_json: bool = typer.Option(False, "--json", help="Print JSON only"),
):
    """Compute metrics from the DB and write docs/results.{md,json}."""
    cfg = load_config(config)
    r = compute_report(cfg.db_path)
    if as_json:
        import json as _json

        typer.echo(_json.dumps(r, indent=2))
        return
    write_report(cfg.db_path, out)
    typer.echo(to_markdown(r))


@app.command()
def simulate_outage(
    minutes: float = typer.Option(7.0, help="Minutes to keep failing"),
    config: str = typer.Option(None),
):
    """Force consecutive failures to test the loud watchdog alert (no real network)."""
    from .health import Watchdog

    cfg = load_config(config)
    setup_logging()
    wd = Watchdog(fail_alert_after_s=cfg.yaml.fail_alert_after_s)
    # Simulate failures fast-forwarded past the threshold.
    wd.failing_since = wd.failing_since or __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    # Backdate to exceed threshold immediately.
    import datetime as dt

    wd.failing_since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=minutes * 60 + 1)
    events = wd.record_failure("simulated outage", "sandbox")
    typer.echo(f"Simulated {minutes} min outage. Loud-alert events fired: {len(events)}")
    for e in events:
        typer.echo(f"  -> {e}")


@app.command("publish-test-release")
def publish_test_release(
    tag: str = typer.Option(None, help="Tag name (default: vYYYYMMDD-HHMM)"),
    config: str = typer.Option(None),
):
    """Publish one synthetic release in the sandbox repo (latency harness)."""
    import httpx

    from .scripts_publish import publish_release

    cfg = load_config(config)
    if not cfg.settings.SANDBOX_REPO or not cfg.settings.SANDBOX_GITHUB_TOKEN:
        typer.echo("SANDBOX_REPO / SANDBOX_GITHUB_TOKEN not set", err=True)
        raise typer.Exit(1)
    if not tag:
        tag = "v" + time.strftime("%Y%m%d-%H%M%S")
    with httpx.Client(timeout=30) as client:
        rel = publish_release(
            client,
            cfg.settings.SANDBOX_REPO,
            cfg.settings.SANDBOX_GITHUB_TOKEN,
            tag,
        )
    typer.echo(f"Published release {tag} (id={rel.get('id')}) at {rel.get('published_at')}")


# Helper module for the publisher used by the CLI and the standalone script.
def _load_publisher():
    return None


if __name__ == "__main__":
    app()
