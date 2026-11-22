"""Processing pipeline (pipes and filters).

collect -> normalize -> de-duplicate -> relevance filter -> PII scrub
        -> sentiment -> tagging -> store -> alerting

Run one collection cycle from the command line with:
    python -m trfd.pipeline
In deployment the same command is scheduled nightly (before 06:00).
"""
import hashlib
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
    author names and profile fields are dropped here."""
    return {
        "source": raw["source"],
        "text": " ".join(raw["text"].split()),
        "posted_at": raw["posted_at"],
    }


def fingerprint(text):
    return hashlib.sha256(re.sub(r"[^a-z0-9]", "", text.lower()).encode()).hexdigest()


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
        r["text"] = scrub_pii(r["text"])
        r["sentiment"], r["confidence"] = sentiment.score(r["text"])
        r.update(tagging.tag(r["text"]))
        out.append(r)
    return out


def run_cycle(db_path=None):
    """One full collection cycle. Returns (records stored, alerts raised)."""
    records = process(collectors.collect_all())
    conn = store.connect(db_path)
    store.reset(conn)
    store.save(conn, records)
    raised = alerts.check(conn)
    conn.close()
    return len(records), raised


if __name__ == "__main__":
    count, raised = run_cycle()
    print(f"Stored {count} feedback records; {len(raised)} alert(s) raised.")
    for a in raised:
        print(f"  ALERT route {a['route']}: {a['negative']} negative items")
