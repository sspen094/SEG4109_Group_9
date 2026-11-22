"""Data access layer: SQLite persistence for feedback records and overrides."""
import os
import sqlite3

DEFAULT_DB = os.environ.get("TRFD_DB", "trfd.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    posted_at    TEXT NOT NULL,
    text         TEXT NOT NULL,
    sentiment    TEXT NOT NULL,
    confidence   REAL NOT NULL,
    route        TEXT,
    stop         TEXT,
    category     TEXT NOT NULL,
    needs_review INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS override_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER NOT NULL REFERENCES feedback(id),
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
FILTERS = ("source", "sentiment", "route", "category")
EDITABLE = ("sentiment", "route", "stop", "category")


def connect(db_path=None):
    conn = sqlite3.connect(db_path or DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def reset(conn):
    conn.execute("DELETE FROM feedback")
    conn.commit()


def save(conn, records):
    conn.executemany(
        "INSERT INTO feedback (source, posted_at, text, sentiment, confidence,"
        " route, stop, category, needs_review) VALUES (:source, :posted_at, :text,"
        " :sentiment, :confidence, :route, :stop, :category, :needs_review)",
        records)
    conn.commit()


def query(conn, **filters):
    clauses, params = [], []
    for key in FILTERS:
        if filters.get(key):
            clauses.append(f"{key} = ?")
            params.append(filters[key])
    if filters.get("needs_review"):
        clauses.append("needs_review = 1")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(f"SELECT * FROM feedback{where} ORDER BY posted_at DESC", params)
    return [dict(r) for r in rows]


def hotspots(conn):
    """Negative feedback grouped by route and issue category, worst first."""
    rows = conn.execute(
        "SELECT route, category, COUNT(*) AS negative FROM feedback"
        " WHERE sentiment = 'negative' AND route IS NOT NULL"
        " GROUP BY route, category ORDER BY negative DESC, route")
    return [dict(r) for r in rows]


def summary(conn):
    rows = conn.execute("SELECT sentiment, COUNT(*) AS n FROM feedback GROUP BY sentiment")
    counts = {r["sentiment"]: r["n"] for r in rows}
    counts["review_queue"] = conn.execute(
        "SELECT COUNT(*) FROM feedback WHERE needs_review = 1").fetchone()[0]
    return counts


def override(conn, feedback_id, changes):
    """Apply a staff override and keep the old value for later retraining."""
    row = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    if row is None:
        return None
    for field, value in changes.items():
        if field not in EDITABLE:
            continue
        conn.execute(
            "INSERT INTO override_log (feedback_id, field, old_value, new_value)"
            " VALUES (?, ?, ?, ?)", (feedback_id, field, row[field], value))
        conn.execute(f"UPDATE feedback SET {field} = ? WHERE id = ?", (value, feedback_id))
    conn.execute(
        "UPDATE feedback SET needs_review = 0 WHERE id = ? AND (route IS NOT NULL"
        " OR stop IS NOT NULL)", (feedback_id,))
    conn.commit()
    return dict(conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone())
