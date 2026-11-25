"""Collection service: one feed per in-scope public source.

Live records come from the Node ingestion package (packages/ingestion), which
calls the official platform APIs and public feeds and appends to
data/reviews.jsonl. A source with no usable live records in that file is
demonstrated on the anonymized sample dataset in data/sample_feedback.json
instead (scope exclusion 10), so the dashboard always runs.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trfd.store import SOURCES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_FILE = DATA_DIR / "sample_feedback.json"
REVIEWS_FILE = Path(os.environ.get("TRFD_REVIEWS_FILE", DATA_DIR / "reviews.jsonl"))
HISTORY_DAYS = int(os.environ.get("TRFD_HISTORY_DAYS", "365"))  # scope exclusion 6

LABELS = {"reddit": "Reddit", "app_store": "App Store", "google_maps": "Google Maps"}
# Source names written by packages/ingestion. Yelp is collected by that package
# but is not one of the three sources in the scope statement (section 4.2), so
# its records are not loaded until a change request adds it.
NODE_SOURCES = {"reddit": "reddit", "app-store": "app_store", "google-maps": "google_maps"}


def _load_sample(source):
    with open(SAMPLE_FILE, encoding="utf-8") as f:
        return [dict(r, origin="sample") for r in json.load(f) if r["source"] == source]


def _timestamp(value):
    """ISO 8601 string from the ingestion package -> UTC 'YYYY-MM-DDTHH:MM:SS'."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _from_ingestion(rec):
    """Raw record in the pipeline's input shape, or None if it can't be used."""
    source = NODE_SOURCES.get(rec.get("source"))
    # Google Places records are collection markers without review text, because
    # Google's terms forbid storing review content (see packages/ingestion).
    if not source or rec.get("recordType", "review") != "review":
        return None
    title, body = (rec.get("title") or "").strip(), (rec.get("text") or "").strip()
    if title and body and title[-1] not in ".!?":
        title += "."
    text = " ".join(p for p in (title, body) if p)
    stamp = rec.get("publishedAt") or rec.get("collectedAt")
    if not text or not stamp:
        return None
    try:
        posted_at = _timestamp(stamp)
    except ValueError:
        return None
    raw = {"source": source, "text": text, "posted_at": posted_at, "origin": "live"}
    if rec.get("locationSpecific") and rec.get("locationName"):
        raw["location_hint"] = rec["locationName"]
    return raw


def load_live(path=None, now=None):
    """{source: [raw records]} from the ingestion JSONL file, last 12 months only."""
    live = {s: [] for s in SOURCES}
    path = Path(path or REVIEWS_FILE)
    if not path.exists():
        return live
    cutoff = ((now or datetime.now(timezone.utc)).replace(tzinfo=None)
              - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                raw = _from_ingestion(json.loads(line)) if line.strip() else None
            except json.JSONDecodeError:
                raw = None
            if raw and raw["posted_at"] >= cutoff:
                live[raw["source"]].append(raw)
    return live


def collect(enabled=None, path=None):
    """Raw records from every enabled source, plus each source's mode:
    'live' (from the ingestion file), 'sample' (fallback) or 'disabled'."""
    enabled = SOURCES if enabled is None else enabled
    live = load_live(path)
    records, status = [], {}
    for source in SOURCES:
        if source not in enabled:
            status[source] = {"mode": "disabled", "records": 0}
            continue
        items = live[source] or _load_sample(source)
        status[source] = {"mode": "live" if live[source] else "sample",
                          "records": len(items)}
        records += items
    return records, status


def collect_all(enabled=None, path=None):
    return collect(enabled, path)[0]
