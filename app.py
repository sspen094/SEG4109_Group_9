"""TRFD web layer: dashboard pages and JSON API (Flask)."""
import json
import os
import secrets
from datetime import date

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   session, url_for)

from trfd import alerts, auth, collectors, pipeline, scheduler, store, tagging

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("TRFD_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
FEEDBACK_PAGE_LIMIT = 200
DATE_RANGES = (("", "All time"), ("30", "Last 30 days"), ("90", "Last 90 days"),
               ("365", "Last 12 months"))


# ---- Request plumbing -------------------------------------------------------

def db():
    if "db" not in g:
        g.db = store.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    if session.get("uid") is not None:
        g.user = store.get_user(db(), session["uid"])
        if g.user is None:
            session.clear()
    # HTML forms carry a per-session token. The JSON API only accepts
    # application/json, which a cross-site form cannot send.
    if request.method == "POST" and not request.path.startswith("/api/"):
        token = session.get("csrf")
        if not token or request.form.get("csrf") != token:
            abort(400, "This form has expired. Reload the page and try again.")


@app.context_processor
def template_globals():
    user = g.get("user")
    context = {"user": user, "can_edit": auth.can(user, "staff"),
               "is_admin": auth.can(user, "admin"), "csrf_token": csrf_token}
    if user:
        context["queue_count"] = store.count(db(), needs_review=True)
    return context


@app.template_filter("label")
def label_filter(value):
    value = str(value or "")
    return collectors.LABELS.get(value) or value.replace("_", " ").capitalize()


@app.template_filter("route_name")
def route_name_filter(route_id):
    return tagging.ROUTE_NAMES.get(route_id, f"Route {route_id}") if route_id else ""


@app.template_filter("period")
def period_filter(iso, granularity="week"):
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.year}" if granularity == "month" else f"Week of {d:%b} {d.day}, {d.year}"


def _safe_next(target, default=None):
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return default or url_for("overview")


def _filters():
    f = {k: request.args.get(k, "").strip() for k in store.FILTERS}
    f["q"] = request.args.get("q", "").strip()
    f["days"] = request.args.get("days", "") if request.args.get("days", "").isdigit() else ""
    f["needs_review"] = request.args.get("needs_review") == "1"
    return f


def _options():
    return {
        "sources": [(s, collectors.LABELS[s]) for s in store.SOURCES],
        "sentiments": store.SENTIMENTS,
        "routes": [(r["route_id"], r["name"]) for r in tagging.ROUTES],
        "stops": tagging.STOP_NAMES,
        "categories": tagging.CATEGORIES,
        "date_ranges": DATE_RANGES,
        "roles": store.ROLES,
    }


def _source_status(conn):
    status = json.loads(store.get_setting(conn, "source_status") or "{}")
    enabled = store.enabled_sources(conn)
    return [{"source": s, "label": collectors.LABELS[s], "enabled": s in enabled,
             **status.get(s, {"mode": "not collected yet", "records": 0})}
            for s in store.SOURCES]


@app.errorhandler(403)
@app.errorhandler(404)
def page_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error=error.description), error.code
    return render_template("error.html", error=error), error.code


# ---- Sign in ----------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = store.authenticate(db(), request.form.get("username", "").strip(),
                                  request.form.get("password", ""))
        if user:
            session.clear()
            session["uid"] = user["id"]
            return redirect(_safe_next(request.args.get("next")))
        flash("Wrong username or password.", "error")
    return render_template(
        "login.html", demo=store.DEMO_PASSWORD == store.DEFAULT_DEMO_PASSWORD,
        demo_password=store.DEFAULT_DEMO_PASSWORD)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---- Dashboard pages ----------------------------------------------------------

@app.get("/")
@auth.require("executive")
def overview():
    conn = db()
    f = {k: v for k, v in _filters().items() if k in ("source", "route", "category", "days")}
    data = {
        "trend": store.trend(conn, **f),
        "byRoute": store.by_route(conn, **f),
        "byCategory": [dict(c, label=label_filter(c["category"]))
                       for c in store.by_category(conn, **f)],
        "stops": store.stop_hotspots(conn, **f),
    }
    return render_template(
        "overview.html", filters=f, options=_options(), data=data,
        summary=store.summary(conn, **f), hotspots=store.hotspots(conn, **f),
        alerts=alerts.check(conn), sources=_source_status(conn),
        alert_threshold=store.get_setting(conn, "alert_threshold"),
        alert_window=store.get_setting(conn, "alert_window_days"))


@app.get("/feedback")
@auth.require("executive")
def feedback():
    conn = db()
    f = _filters()
    return render_template(
        "feedback.html", filters=f, options=_options(), total=store.count(conn, **f),
        rows=store.query(conn, limit=FEEDBACK_PAGE_LIMIT, **f),
        limit=FEEDBACK_PAGE_LIMIT, here=request.full_path.rstrip("?"))


@app.route("/feedback/<int:feedback_id>", methods=["GET", "POST"])
@auth.require("executive")
def feedback_item(feedback_id):
    conn = db()
    item = store.get(conn, feedback_id)
    if item is None:
        abort(404, "No feedback item with that ID.")
    back = _safe_next(request.values.get("next"), url_for("feedback"))
    if request.method == "POST":
        if not auth.can(g.user, "staff"):
            abort(403, "Executives have read-only access.")
        changes = {k: request.form.get(k, "") for k in store.EDITABLE}
        try:
            store.override(conn, feedback_id, changes, g.user["username"])
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("feedback_item", feedback_id=feedback_id, next=back))
        flash(f"Item {feedback_id} saved. Changes are logged for retraining.", "ok")
        return redirect(back)
    return render_template("item.html", item=item, history=store.history(conn, feedback_id),
                           options=_options(), back=back)


# ---- Administration -------------------------------------------------------------

@app.get("/admin")
@auth.require("admin")
def admin():
    conn = db()
    return render_template(
        "admin.html", sources=_source_status(conn), users=store.list_users(conn),
        runs=store.recent_runs(conn, 15), streak=store.nightly_streak(conn),
        on_time=store.finished_on_time, options=_options(),
        alert_threshold=store.get_setting(conn, "alert_threshold"),
        alert_window=store.get_setting(conn, "alert_window_days"),
        run_at=scheduler.RUN_AT, scheduler_on=os.environ.get("TRFD_SCHEDULER") == "1")


@app.post("/admin/settings")
@auth.require("admin")
def admin_settings():
    conn = db()
    threshold, window = request.form.get("alert_threshold", ""), request.form.get(
        "alert_window_days", "")
    sources = [s for s in store.SOURCES if request.form.get(f"source_{s}")]
    if not (threshold.isdigit() and int(threshold) >= 1):
        flash("The alert threshold must be a whole number of at least 1.", "error")
    elif not (window.isdigit() and int(window) <= 365):
        flash("The alert window must be 0 to 365 days (0 counts all feedback).", "error")
    elif not sources:
        flash("Keep at least one data source enabled.", "error")
    else:
        store.set_setting(conn, "alert_threshold", int(threshold))
        store.set_setting(conn, "alert_window_days", int(window))
        store.set_setting(conn, "sources_enabled", ",".join(sources))
        flash("Settings saved. Source changes apply from the next collection cycle.", "ok")
    return redirect(url_for("admin"))


@app.post("/admin/users")
@auth.require("admin")
def admin_add_user():
    try:
        store.create_user(db(), request.form.get("username"), request.form.get("password"),
                          request.form.get("role"))
        flash(f"User {request.form.get('username', '').strip()} added.", "ok")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin"))


@app.post("/admin/users/<int:user_id>/delete")
@auth.require("admin")
def admin_delete_user(user_id):
    if user_id == g.user["id"]:
        flash("You cannot delete your own account.", "error")
    else:
        store.delete_user(db(), user_id)
        flash("User deleted.", "ok")
    return redirect(url_for("admin"))


@app.post("/admin/run")
@auth.require("admin")
def admin_run():
    ingestion = scheduler.run_ingestion() if request.form.get("ingest") else "not run"
    try:
        stored, raised = pipeline.run_cycle(kind="manual", note=f"ingestion {ingestion}")
        flash(f"Collection cycle finished: {stored} new item(s), {len(raised)} alert(s)."
              f" Node ingestion: {ingestion}.", "ok")
    except Exception as exc:  # logged in the runs table by the pipeline
        flash(f"Collection cycle failed: {exc}", "error")
    return redirect(url_for("admin"))


# ---- JSON API -------------------------------------------------------------------

@app.get("/api/feedback")
@auth.require("executive")
def api_feedback():
    return jsonify(store.query(db(), **_filters()))


@app.get("/api/hotspots")
@auth.require("executive")
def api_hotspots():
    conn = db()
    return jsonify(hotspots=store.hotspots(conn), stops=store.stop_hotspots(conn),
                   alerts=alerts.check(conn))


@app.post("/api/feedback/<int:feedback_id>/override")
@auth.require("staff")
def api_override(feedback_id):
    changes = request.get_json(silent=True) if request.is_json else None
    if not isinstance(changes, dict):
        return jsonify(error="Send a JSON object, for example {\"route\": \"97\"}."), 415
    try:
        row = store.override(db(), feedback_id, changes, g.user["username"])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if row is None:
        abort(404, "No feedback item with that ID.")
    return jsonify(row)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    stored, raised = pipeline.run_cycle(kind="startup")
    print(f"Collection cycle: {stored} new records stored, {len(raised)} alert(s).")
    if os.environ.get("TRFD_SCHEDULER") == "1":
        scheduler.start_background()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
