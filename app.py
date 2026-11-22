"""TRFD web layer: dashboard page and JSON API (Flask)."""
import os

from flask import Flask, abort, jsonify, render_template, request

from trfd import alerts, pipeline, store

app = Flask(__name__)


def _filters():
    return {k: request.args.get(k, "").strip() for k in store.FILTERS} | {
        "needs_review": request.args.get("needs_review") == "1"}


@app.get("/")
def dashboard():
    conn = store.connect()
    filters = _filters()
    page = render_template(
        "index.html",
        filters=filters,
        summary=store.summary(conn),
        hotspots=store.hotspots(conn),
        alerts=alerts.check(conn),
        feedback=store.query(conn, **filters),
        routes=[r[0] for r in conn.execute(
            "SELECT DISTINCT route FROM feedback WHERE route IS NOT NULL ORDER BY CAST(route AS INTEGER)")],
        categories=[r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM feedback ORDER BY category")],
    )
    conn.close()
    return page


@app.get("/api/feedback")
def api_feedback():
    conn = store.connect()
    rows = store.query(conn, **_filters())
    conn.close()
    return jsonify(rows)


@app.get("/api/hotspots")
def api_hotspots():
    conn = store.connect()
    data = {"hotspots": store.hotspots(conn), "alerts": alerts.check(conn)}
    conn.close()
    return jsonify(data)


@app.post("/api/feedback/<int:feedback_id>/override")
def api_override(feedback_id):
    changes = request.get_json(silent=True) or {}
    conn = store.connect()
    row = store.override(conn, feedback_id, changes)
    conn.close()
    if row is None:
        abort(404)
    return jsonify(row)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    stored, raised = pipeline.run_cycle()
    print(f"Collection cycle: {stored} records stored, {len(raised)} alert(s).")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
