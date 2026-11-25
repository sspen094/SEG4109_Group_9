"""Nightly collection scheduler (WBS 1.5.7; TR1 and TR8).

A full cycle runs the Node ingestion package (packages/ingestion) to append
new public feedback to data/reviews.jsonl, then the Python pipeline to clean,
score, tag and store it. A failed cycle is retried with back-off (R1.5), and
every attempt is logged in the runs table shown on the Admin page.

    python -m trfd.scheduler          # run every day at TRFD_RUN_AT (default 02:00)
    python -m trfd.scheduler --once   # run one nightly cycle now (for Task Scheduler/cron)

The web app starts the same loop in a background thread when TRFD_SCHEDULER=1.
"""
import argparse
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from trfd import collectors, pipeline

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "packages" / "ingestion" / "src" / "cli.js"
RUN_AT = os.environ.get("TRFD_RUN_AT", "02:00")
RETRY_DELAYS = (300, 900, 1800)  # seconds to wait before each retry


def ingest_config():
    if os.environ.get("TRFD_INGEST_CONFIG"):
        return Path(os.environ["TRFD_INGEST_CONFIG"])
    local = ROOT / "packages" / "ingestion" / "locations.json"
    return local if local.exists() else local.with_name("locations.example.json")


def run_ingestion(timeout=600):
    """Run the Node ingestion CLI. Returns a short status; never raises, so a
    source outage still lets the pipeline run on the data already collected."""
    node, config = shutil.which("node"), ingest_config()
    if not node or not CLI.exists():
        return "skipped (Node.js not available)"
    if not config.exists():
        return f"skipped (no locations file at {config})"
    try:
        result = subprocess.run(
            [node, str(CLI), str(config), str(collectors.REVIEWS_FILE)], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"failed ({exc})"
    try:
        summary = json.loads(result.stdout)
        detail = f"{summary['fetched']} fetched, {summary['stored']} new"
        if summary["errors"]:
            detail += f", {len(summary['errors'])} source error(s)"
    except (ValueError, KeyError, TypeError):
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1][:200] if lines else f"exit code {result.returncode}"
    return f"{'ok' if result.returncode == 0 else 'with errors'} ({detail})"


def nightly_cycle(db_path=None, kind="nightly"):
    ingestion = run_ingestion()
    stored, raised = pipeline.run_cycle(db_path, kind=kind, note=f"ingestion {ingestion}")
    return ingestion, stored, raised


def next_run(now, run_at=RUN_AT):
    hour, minute = (int(p) for p in run_at.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def run_with_retries(db_path=None, sleep=time.sleep):
    for attempt, delay in enumerate((0,) + RETRY_DELAYS, start=1):
        if delay:
            sleep(delay)
        try:
            return nightly_cycle(db_path)
        except Exception as exc:  # the failed run is already in the runs table
            print(f"[scheduler] attempt {attempt} failed: {exc}", flush=True)
    return None


def serve_forever(db_path=None):
    while True:
        target = next_run(datetime.now())
        print(f"[scheduler] next collection cycle at {target:%Y-%m-%d %H:%M}", flush=True)
        while (remaining := (target - datetime.now()).total_seconds()) > 0:
            time.sleep(min(remaining, 300))
        run_with_retries(db_path)


def start_background(db_path=None):
    thread = threading.Thread(target=serve_forever, args=(db_path,),
                              name="trfd-scheduler", daemon=True)
    thread.start()
    return thread


def main(argv=None):
    parser = argparse.ArgumentParser(description="TRFD nightly collection scheduler")
    parser.add_argument("--once", action="store_true", help="run one nightly cycle now")
    if parser.parse_args(argv).once:
        ingestion, stored, raised = nightly_cycle()
        print(f"Ingestion {ingestion}. Stored {stored} new item(s); {len(raised)} alert(s).")
    else:
        serve_forever()


if __name__ == "__main__":
    main()
