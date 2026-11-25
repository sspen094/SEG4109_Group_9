"""Processing pipeline (pipes and filters).

collect -> normalize -> de-duplicate -> relevance filter -> PII scrub
        -> sentiment -> tagging -> store -> alerting

Run one pipeline cycle from the command line with:
    python -m trfd.pipeline
The nightly scheduler (trfd/scheduler.py) runs the Node ingestion package
first and then this cycle, finishing before 06:00 (TR8).
"""
import json
import re

from trfd import alerts, collectors, sentiment, store, tagging

TRANSIT_TERMS = re.compile(
    r"\b(bus|buses|route|stop|station|o-?train|lrt|train|transit|oc ?transpo|"
    r"presto|driver|platform|line \d|trillium|confederation|fares?)\b", re.I)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
HANDLE = re.compile(r"(?<![\w/])(?:/?u/|@)[A-Za-z0-9_-]{2,}")
PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")


def normalize(raw):
    """Unified feedback record. Only text, timestamp and source are kept;
    author names and profile fields are dropped here. A location hint from
    the collector is passed to the tagging step and is not stored."""
    record = {
        "source": raw["source"],
        "text": " ".join(raw["text"].split()),
        "posted_at": raw["posted_at"],
    }
    if raw.get("location_hint"):
        record["location_hint"] = raw["location_hint"]
    if raw.get("origin"):
        record["origin"] = raw["origin"]  # "live" or "sample" dataset
    return record


fingerprint = store.fingerprint


def deduplicate(records):
    seen, unique = set(), []
    for r in records:
        fp = fingerprint(r["text"])
        if fp not in seen:
            seen.add(fp)
            unique.append(r)
    return unique


def is_transit_relevant(text):
    return bool(TRANSIT_TERMS.search(text) or tagging.resolve_route(text)
                or tagging.resolve_stop(text))


def scrub_pii(text):
    text = EMAIL.sub("[email removed]", text)
    text = HANDLE.sub("[user removed]", text)
    return PHONE.sub("[phone removed]", text)


def process(raw_records):
    records = deduplicate([normalize(r) for r in raw_records])
    # App Store and Google Maps reviews are already about the agency's app or
    # stations; only Reddit posts from general subreddits need the filter.
    records = [r for r in records
               if r["source"] != "reddit" or is_transit_relevant(r["text"])]
    out = []
    for r in records:
        hint = r.pop("location_hint", None)
        r["text"] = scrub_pii(r["text"])
        r["sentiment"], r["confidence"] = sentiment.score(r["text"])
        r.update(tagging.tag(r["text"], hint, r["source"]))
        out.append(r)
    return out


def located_share(records):
    """Share of location-specific items tagged to a route or stop without
    staff help (acceptance criterion 3 asks for at least 70%)."""
    specific = [r for r in records if r["category"] not in tagging.SYSTEM_WIDE]
    if not specific:
        return None
    return round(100 * sum(1 for r in specific if r["route"] or r["stop"]) / len(specific))


def run_cycle(db_path=None, kind="manual", note=""):
    """One pipeline cycle: collect, process, store new items, check alerts.
    Logged in the runs table. Returns (new records stored, alerts raised)."""
    conn = store.connect(db_path)
    run_id = store.start_run(conn, kind)
    try:
        raw, status = collectors.collect(store.enabled_sources(conn))
        records = process(raw)
        removed = sum(store.purge_sample(conn, source)
                      for source, info in status.items() if info["mode"] == "live")
        stored = store.save(conn, records)
        store.set_setting(conn, "source_status", json.dumps(status))
        raised = alerts.check(conn)
        share = located_share(records)
        message = "; ".join(p for p in (
            f"{len(records)} processed, {stored} new",
            f"{removed} sample items replaced by live data" if removed else "",
            f"{share}% of location-specific items auto-tagged" if share is not None else "",
            note) if p)
        store.finish_run(conn, run_id, "ok", stored, len(raised), message)
        return stored, raised
    except Exception as exc:
        store.finish_run(conn, run_id, "failed", message=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    count, raised = run_cycle()
    print(f"Stored {count} new feedback records; {len(raised)} alert(s) raised.")
    for a in raised:
        print(f"  ALERT route {a['route']}: {a['negative']} negative items")
