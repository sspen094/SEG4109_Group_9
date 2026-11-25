"""Threshold-based alerting on negative feedback volume per route.

An administrator sets the threshold and the time window on the Admin page
(TR6); TRFD_ALERT_THRESHOLD only sets the starting threshold. The window is
counted back from the most recent collected item, because collection is a
daily batch. Alerts appear on the dashboard and in the pipeline log;
emailing the responsible manager is planned for deployment.
"""
from trfd import store


def check(conn, threshold=None, window_days=None):
    limit = int(threshold or store.get_setting(conn, "alert_threshold"))
    days = int(window_days if window_days is not None
               else store.get_setting(conn, "alert_window_days"))
    window, params = "", []
    if days > 0:
        window = (" AND posted_at >= (SELECT strftime('%Y-%m-%dT%H:%M:%S',"
                  " MAX(posted_at), ?) FROM feedback)")
        params.append(f"-{days} days")
    rows = conn.execute(
        "SELECT route, COUNT(*) AS negative FROM feedback"
        f" WHERE sentiment = 'negative' AND route IS NOT NULL{window}"
        " GROUP BY route HAVING COUNT(*) >= ? ORDER BY negative DESC, route",
        params + [limit])
    return [dict(r) for r in rows]
