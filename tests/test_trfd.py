"""Unit and integration tests for the TRFD prototype. Run with: python -m pytest"""
import json
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from trfd import (alerts, collectors, gtfs, pipeline, scheduler, sentiment,  # noqa: E402
                  store, tagging)


@pytest.fixture(autouse=True)
def sample_data_only(tmp_path, monkeypatch):
    """Keep tests on the sample dataset even if data/reviews.jsonl exists locally."""
    monkeypatch.setattr(collectors, "REVIEWS_FILE", tmp_path / "no-live-data.jsonl")


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
    ("The 88 was a ghost bus", "88"),
    ("Route 61 was packed", "61"),
    ("Thanks LRT", "1"),
    ("Trillium Line is quick", "2"),
    ("Line 4 to the airport was empty", "4"),
    ("The R1 shuttle skipped Hurdman", "R1"),
    ("waited 30 minutes", None),
    ("the 20 minute wait again", None),
    ("caught the 7:15 bus", None),
    ("The 97 was retired in 2025", None),  # not in the current GTFS feed
])
def test_route_resolution(text, route):
    assert tagging.resolve_route(text) == route


def test_reference_data_covers_the_whole_network():
    assert {"1", "2", "4"} <= tagging.ROUTE_IDS and len(tagging.ROUTES) > 150
    assert tagging.ROUTE_NAMES["4"] == "O-Train Line 4"
    assert len(tagging.STOPS) > 50 and all(s["aliases"] and s["lat"] for s in tagging.STOPS)
    assert tagging.tag("The escalator at Pimisi is broken")["route"] == "1"
    assert tagging.tag("Uplands station platform was icy")["route"] == "4"
    bayview = tagging.tag("Bayview station was packed")  # served by Lines 1 and 2
    assert bayview["stop"] == "Bayview" and bayview["route"] is None
    assert not bayview["needs_review"]
    assert tagging.resolve_stop("Stuck at Tunney’s again") == "Tunney's Pasture"


def test_gtfs_loader_builds_routes_and_stations(tmp_path):
    def table(header, *rows):
        return "\n".join((header,) + rows) + "\n"

    feed = tmp_path / "feed.zip"
    with zipfile.ZipFile(feed, "w") as z:
        z.writestr("routes.txt", table(
            "route_id,route_short_name,route_long_name,route_type",
            "1-373,1,Blair <> Tunney's Pasture,0", "2-354,2,Bayview <> Limebank,0",
            "R1,R1,Tunney's Pasture <> Blair,3", "88,88,Hurdman <> Bayshore,3"))
        z.writestr("stops.txt", table(
            "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station",
            "S1,TUNNEY'S PASTURE,45.4036,-75.7368,1,", "S1A,TUNNEY'S PASTURE 1A,45.4,-75.7,0,S1",
            "S2,BAYVIEW,45.4089,-75.7223,1,", "S2A,BAYVIEW 1,45.4,-75.7,0,S2",
            "S2B,BAYVIEW 2,45.4,-75.7,0,S2", "S3,PARLIAMENT ~ PARLEMENT,45.4213,-75.699,1,",
            "B1,BANK / SOMERSET,45.41,-75.69,0,"))
        z.writestr("trips.txt", table("route_id,service_id,trip_id",
                                      "1-373,WK,T1", "2-354,WK,T2", "88,WK,T3"))
        z.writestr("stop_times.txt", table(
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence",
            "T1,08:00:00,08:00:00,S1A,1", "T1,08:05:00,08:05:00,S2A,2",
            "T1,08:09:00,08:09:00,S3,3", "T2,08:00:00,08:00:00,S2B,1",
            "T3,08:00:00,08:00:00,B1,1"))
    (tmp_path / "stops.csv").write_text(
        "stop_name,route_id,aliases,lat,lon\nTunney's Pasture,1,Tunney's|Tunneys,0,0\n",
        encoding="utf-8")
    routes, stations = gtfs.build(feed, data_dir=tmp_path)
    assert [r["route_id"] for r in routes] == ["1", "2", "88", "R1"]
    assert routes[0]["name"] == "O-Train Line 1" and "Confederation Line" in routes[0]["aliases"]
    assert routes[2]["aliases"] == "" and routes[3]["aliases"] == "R1"
    by_name = {s["stop_name"]: s for s in stations}
    assert set(by_name) == {"Tunney's Pasture", "Bayview", "Parliament"}  # no street corners
    assert by_name["Tunney's Pasture"]["route_id"] == "1"
    assert "Tunney's" in by_name["Tunney's Pasture"]["aliases"].split("|")  # kept from CSV
    assert by_name["Bayview"]["route_id"] == "" and by_name["Bayview"]["lines"] == "1 2"
    assert "station Parlement" in by_name["Parliament"]["aliases"].split("|")
    assert (tmp_path / "routes.csv").read_text(encoding="utf-8").startswith("route_id,name")


def test_colloquial_stop_name():
    assert tagging.resolve_stop("Stuck at Tunney's again") == "Tunney's Pasture"


def test_vague_feedback_goes_to_manual_queue():
    tags = tagging.tag("The bus at the downtown station was dirty.")
    assert tags["needs_review"] and tags["category"] == "cleanliness"


def test_app_feedback_does_not_need_a_location():
    assert not tagging.tag("App crashes every time I open the trip planner.")["needs_review"]
    review = tagging.tag("How the heck? Not easy to use", source="app_store")
    assert review["category"] == "app_quality" and not review["needs_review"]


# ---- Integration: full cycle, store, alerts, API ---------------------------

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    pipeline.run_cycle(path)
    return path


@pytest.fixture
def conn(db):
    connection = store.connect(db)
    yield connection
    connection.close()


def test_full_cycle_stores_clean_records(conn):
    rows = store.query(conn)
    assert len(rows) == len(collectors.collect_all()) - 2  # 1 duplicate, 1 off-topic
    assert not any("@example.com" in r["text"] or "555-0142" in r["text"] for r in rows)
    assert alerts.check(conn)[0]["route"] == "1"


def test_last_successful_run_ignores_failed_and_running_runs(conn):
    successful_run = store.last_successful_run(conn)
    assert successful_run

    failed_id = store.start_run(conn, "manual")
    store.finish_run(conn, failed_id, "failed")
    store.start_run(conn, "manual")

    assert store.last_successful_run(conn) == successful_run


def test_override_is_logged(conn):
    item = store.query(conn, needs_review=True)[0]
    updated = store.override(conn, item["id"], {"route": "7"})
    assert updated["route"] == "7" and updated["needs_review"] == 0
    log = conn.execute("SELECT * FROM override_log").fetchall()
    assert len(log) == 1 and log[0]["new_value"] == "7"


def login(client, username, password=store.DEMO_PASSWORD):
    with client.session_transaction() as s:
        s["csrf"] = "test-token"
    return client.post("/login", data={"username": username, "password": password,
                                       "csrf": "test-token"})


def form_post(client, url, data):
    with client.session_transaction() as s:
        s["csrf"] = "test-token"
    return client.post(url, data=dict(data, csrf="test-token"))


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB", db)
    from app import app
    return app.test_client()


def test_api_endpoints(client):
    assert client.get("/health").get_json() == {"status": "ok"}
    login(client, "staff")
    overview = client.get("/")
    assert overview.status_code == 200
    assert b"Key takeaways" in overview.data
    assert b"Last successful collection" in overview.data
    assert b"Most negative route and issue" in overview.data
    negatives = client.get("/api/feedback?sentiment=negative").get_json()
    assert negatives and all(r["sentiment"] == "negative" for r in negatives)
    assert client.get("/api/hotspots").get_json()["alerts"]
    assert client.post("/api/feedback/9999/override", json={"route": "1"}).status_code == 404


# ---- Bridge from the Node ingestion package ---------------------------------

def _jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_ingestion_records_replace_the_sample_for_their_source(tmp_path):
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    path = _jsonl(tmp_path / "reviews.jsonl", [
        {"id": "app-store:1", "recordType": "review", "source": "app-store",
         "title": "Crashes", "text": "The app crashes on launch", "publishedAt": recent},
        {"id": "reddit:t3_a", "recordType": "review", "source": "reddit", "title": "Platform",
         "text": "Packed again", "publishedAt": recent, "locationSpecific": True,
         "locationName": "Parliament Station"},
        {"id": "google-maps:x", "recordType": "collection-reference", "source": "google-maps"},
        {"id": "yelp:1", "recordType": "review", "source": "yelp", "text": "Out of scope",
         "publishedAt": recent},
        {"id": "app-store:old", "recordType": "review", "source": "app-store",
         "text": "Older than twelve months", "publishedAt": "2020-01-01T00:00:00Z"},
    ])
    records, status = collectors.collect(path=path)
    app_items = [r for r in records if r["source"] == "app_store"]
    assert app_items == [{"source": "app_store", "text": "Crashes. The app crashes on launch",
                          "posted_at": recent[:19], "origin": "live"}]
    assert status["app_store"] == {"mode": "live", "records": 1}
    assert status["google_maps"]["mode"] == "sample"  # no stored review text
    assert not any(r["text"] == "Out of scope" for r in records)  # Yelp is out of scope
    reddit = [r for r in records if r["source"] == "reddit"]
    assert reddit[0]["location_hint"] == "Parliament Station"


def test_location_hint_resolves_the_stop_when_the_text_names_none():
    tags = tagging.tag("Platform was packed again", hint="Parliament Station")
    assert tags["stop"] == "Parliament"
    record = pipeline.process([{"source": "reddit", "posted_at": "2026-11-20T10:00:00",
                                "text": "The train platform was packed again",
                                "location_hint": "Parliament Station"}])[0]
    assert record["stop"] == "Parliament" and "location_hint" not in record


def test_sample_items_are_replaced_once_a_source_goes_live(db, conn, monkeypatch, tmp_path):
    sample = store.query(conn, source="app_store")
    assert sample and {r["origin"] for r in sample} == {"sample"}
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    monkeypatch.setattr(collectors, "REVIEWS_FILE", _jsonl(tmp_path / "live.jsonl", [
        {"id": "app-store:9", "recordType": "review", "source": "app-store",
         "text": "Trip planner keeps freezing", "publishedAt": recent}]))
    pipeline.run_cycle(db)
    rows = store.query(conn, source="app_store")
    assert [(r["origin"], r["text"]) for r in rows] == [("live", "Trip planner keeps freezing")]
    assert store.query(conn, source="reddit")  # sources still on sample data are untouched


def test_sample_items_follow_the_sample_file(db, conn, monkeypatch, tmp_path):
    sample = json.loads(collectors.SAMPLE_FILE.read_text(encoding="utf-8"))
    changed = [r for r in sample if r["source"] != "google_maps"] + [{
        "source": "google_maps", "posted_at": "2026-11-20T10:00:00",
        "text": "Pimisi station elevator is out of order again."}]
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(collectors, "SAMPLE_FILE", path)
    pipeline.run_cycle(db)
    google = store.query(conn, source="google_maps")
    assert [(r["text"], r["stop"], r["route"]) for r in google] == [
        ("Pimisi station elevator is out of order again.", "Pimisi", "1")]


def test_stored_tags_follow_a_new_route_list(db, conn):
    stale = store.query(conn, stop="Hurdman")[0]
    conn.execute("UPDATE feedback SET route = '97' WHERE id = ?", (stale["id"],))
    conn.commit()
    corrected = store.query(conn, needs_review=True)[0]
    store.override(conn, corrected["id"], {"route": "7"}, "staff")
    store.set_setting(conn, "reference_version", "an-older-feed")
    pipeline.run_cycle(db)
    assert store.get(conn, stale["id"])["route"] == "1"  # re-tagged from its text
    assert store.get(conn, corrected["id"])["route"] == "7"  # staff changes are kept
    assert "re-tagged" in store.recent_runs(conn, 1)[0]["message"]


def test_disabled_sources_are_not_collected():
    records, status = collectors.collect(enabled=["reddit"])
    assert {r["source"] for r in records} == {"reddit"}
    assert status["app_store"]["mode"] == "disabled"


# ---- Incremental storage, overrides, settings ---------------------------------

def test_cycles_are_incremental_and_keep_staff_overrides(db, conn):
    before = store.count(conn)
    item = store.query(conn, needs_review=True)[0]
    store.override(conn, item["id"], {"sentiment": "positive"}, "staff")
    stored, _ = pipeline.run_cycle(db)
    assert stored == 0 and store.count(conn) == before
    kept = store.get(conn, item["id"])
    assert kept["sentiment"] == "positive" and kept["confidence"] == 1.0


def test_invalid_override_is_rejected(conn):
    with pytest.raises(ValueError):
        store.override(conn, 1, {"route": "999"})
    with pytest.raises(ValueError):
        store.override(conn, 1, {"sentiment": "angry"})


def test_alert_threshold_and_window_come_from_settings(conn):
    store.set_setting(conn, "alert_threshold", 100)
    assert alerts.check(conn) == []
    store.set_setting(conn, "alert_threshold", 2)
    assert alerts.check(conn, window_days=0)
    assert alerts.check(conn, window_days=1) == []  # too few items in the latest day


def test_weekly_trend_buckets_start_on_monday(conn):
    now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    rows = conn.execute("SELECT id FROM feedback ORDER BY id").fetchall()
    for index, row in enumerate(rows):
        posted_at = (now - timedelta(days=index % 28)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("UPDATE feedback SET posted_at = ? WHERE id = ?", (posted_at, row["id"]))
    conn.commit()
    t = store.trend(conn)
    assert t["granularity"] == "week"
    assert all(datetime.fromisoformat(p).weekday() == 0 for p in t["periods"])
    assert sum(sum(v) for v in t["series"].values()) == store.count(conn)


def test_stop_hotspots_have_coordinates(conn):
    stops = store.stop_hotspots(conn)
    hurdman = next(s for s in stops if s["stop"] == "Hurdman")
    assert hurdman["negative"] >= 1 and 45 < hurdman["lat"] < 46


def test_run_log_and_nightly_streak(conn):
    assert store.recent_runs(conn)[0]["status"] == "ok"
    for day, end in (("2026-11-20", "02:10:00"), ("2026-11-21", "07:00:00"),
                     ("2026-11-22", "02:10:00"), ("2026-11-23", "02:12:00")):
        conn.execute("INSERT INTO runs (kind, started_at, finished_at, status)"
                     " VALUES ('nightly', ?, ?, 'ok')", (f"{day}T02:00:00", f"{day}T{end}"))
    conn.commit()
    assert store.nightly_streak(conn) == 2  # Nov 21 finished after 06:00 (TR8)


def test_scheduler_next_run_and_missing_node(monkeypatch):
    assert scheduler.next_run(datetime(2026, 11, 25, 1, 0)) == datetime(2026, 11, 25, 2, 0)
    assert scheduler.next_run(datetime(2026, 11, 25, 3, 0)) == datetime(2026, 11, 26, 2, 0)
    monkeypatch.setattr(scheduler.shutil, "which", lambda _name: None)
    assert scheduler.run_ingestion().startswith("skipped")


# ---- Role-based access (TR6) and forms -------------------------------------------

def test_sign_in_is_required(client):
    assert client.get("/").status_code == 302
    assert client.get("/api/feedback").status_code == 401
    assert login(client, "staff", "wrong-password").status_code == 200  # form shown again
    assert client.get("/").status_code == 302


def test_executives_are_read_only(client):
    login(client, "executive")
    assert client.get("/feedback/1").status_code == 200
    assert client.post("/api/feedback/1/override", json={"route": "1"}).status_code == 403
    assert form_post(client, "/feedback/1", {"route": "1"}).status_code == 403
    assert client.get("/admin").status_code == 403


def test_staff_can_retag_through_the_form(client, conn):
    login(client, "staff")
    item = store.query(conn, needs_review=True)[0]
    response = form_post(client, f"/feedback/{item['id']}", {
        "sentiment": item["sentiment"], "route": "7", "stop": "", "category": item["category"],
        "next": "/feedback?needs_review=1"})
    assert response.status_code == 302 and response.headers["Location"].endswith("needs_review=1")
    updated = store.get(conn, item["id"])
    assert updated["route"] == "7" and updated["needs_review"] == 0
    assert store.history(conn, item["id"])[0]["changed_by"] == "staff"
    assert client.get("/admin").status_code == 403


def test_forms_need_the_csrf_token(client):
    login(client, "admin")
    assert client.post("/admin/settings", data={"alert_threshold": "5"}).status_code == 400


def test_admin_manages_settings_and_users(client, conn):
    login(client, "admin")
    assert client.get("/admin").status_code == 200
    form_post(client, "/admin/settings", {"alert_threshold": "9", "alert_window_days": "0",
                                          "source_reddit": "1"})
    assert store.get_setting(conn, "alert_threshold") == "9"
    assert store.enabled_sources(conn) == ["reddit"]
    form_post(client, "/admin/users", {"username": "liam", "password": "pw", "role": "staff"})
    assert store.authenticate(conn, "liam", "pw")["role"] == "staff"


def test_pages_load_fast_with_a_year_of_feedback(client, conn):
    """TR7: pages load in under 3 s with 12 months of feedback."""
    start = datetime.now() - timedelta(days=365)
    store.save(conn, [{
        "source": "reddit", "text": f"The 88 bus was late again, report {i}",
        "posted_at": (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
        "sentiment": "negative", "confidence": 0.7, "route": "88", "stop": None,
        "category": "delays", "needs_review": False} for i in range(8000)])
    login(client, "executive")
    for path in ("/", "/feedback", "/feedback?route=88"):
        began = time.perf_counter()
        assert client.get(path).status_code == 200
        assert time.perf_counter() - began < 3
