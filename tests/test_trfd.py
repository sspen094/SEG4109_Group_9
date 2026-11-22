"""Unit and integration tests for the TRFD prototype. Run with: python -m pytest"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from trfd import alerts, collectors, pipeline, sentiment, store, tagging  # noqa: E402


# ---- Pipeline filters ------------------------------------------------------

def test_pii_scrubber_removes_handles_emails_and_phones():
    text = "u/someone says call 613-555-0142 or email a.b@example.com"
    clean = pipeline.scrub_pii(text)
    assert "someone" not in clean and "555" not in clean and "example.com" not in clean
    assert "[user removed]" in clean and "[phone removed]" in clean and "[email removed]" in clean


def test_normalize_drops_author():
    raw = {"source": "reddit", "author": "x", "posted_at": "2026-11-01", "text": " a   b "}
    assert pipeline.normalize(raw) == {"source": "reddit", "posted_at": "2026-11-01", "text": "a b"}


def test_cross_source_duplicates_are_removed():
    records = [{"text": "Hurdman is filthy."}, {"text": "hurdman is FILTHY!"}]
    assert len(pipeline.deduplicate(records)) == 1


def test_off_topic_posts_are_filtered():
    assert not pipeline.is_transit_relevant("Anyone know good brunch spots near the Glebe?")
    assert pipeline.is_transit_relevant("The 97 bus was late")


# ---- Sentiment engine ------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Blair station is clean and the staff were helpful.", "positive"),
    ("Driver on the 88 was rude.", "negative"),
    ("The platform is not clean.", "negative"),
    ("Thanks LRT for being late again.", "negative"),  # sarcasm
    ("The 88 is never late.", "positive"),
    ("App is fine I guess.", "neutral"),
])
def test_sentiment_labels(text, expected):
    label, confidence = sentiment.score(text)
    assert label == expected
    assert 0 < confidence <= 0.95


# ---- Tagging module --------------------------------------------------------

@pytest.mark.parametrize("text, route", [
    ("The 97 was a ghost bus", "97"),
    ("Route 61 was packed", "61"),
    ("Thanks LRT", "1"),
    ("Trillium Line is quick", "2"),
    ("waited 30 minutes", None),
])
def test_route_resolution(text, route):
    assert tagging.resolve_route(text) == route


def test_colloquial_stop_name():
    assert tagging.resolve_stop("Stuck at Tunney's again") == "Tunney's Pasture"


def test_vague_feedback_goes_to_manual_queue():
    tags = tagging.tag("The bus at the downtown station was dirty.")
    assert tags["needs_review"] and tags["category"] == "cleanliness"


def test_app_feedback_does_not_need_a_location():
    assert not tagging.tag("App crashes every time I open the trip planner.")["needs_review"]


# ---- Integration: full cycle, store, alerts, API ---------------------------

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    pipeline.run_cycle(path)
    return path


def test_full_cycle_stores_clean_records(db):
    conn = store.connect(db)
    rows = store.query(conn)
    assert len(rows) == len(collectors.collect_all()) - 2  # 1 duplicate, 1 off-topic
    assert not any("@example.com" in r["text"] or "555-0142" in r["text"] for r in rows)
    assert alerts.check(conn)[0]["route"] == "1"


def test_override_is_logged(db):
    conn = store.connect(db)
    item = store.query(conn, needs_review=True)[0]
    updated = store.override(conn, item["id"], {"route": "7"})
    assert updated["route"] == "7" and updated["needs_review"] == 0
    log = conn.execute("SELECT * FROM override_log").fetchall()
    assert len(log) == 1 and log[0]["new_value"] == "7"


def test_api_endpoints(db, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB", db)
    from app import app
    client = app.test_client()
    assert client.get("/health").get_json() == {"status": "ok"}
    assert client.get("/").status_code == 200
    negatives = client.get("/api/feedback?sentiment=negative").get_json()
    assert negatives and all(r["sentiment"] == "negative" for r in negatives)
    assert client.get("/api/hotspots").get_json()["alerts"]
    assert client.post("/api/feedback/9999/override", json={"route": "1"}).status_code == 404
