"""Threshold-based alerting on negative feedback volume per route.

The prototype returns alerts to the dashboard and prints them in the
pipeline log. Emailing the responsible manager is planned for deployment.
"""
import os

THRESHOLD = int(os.environ.get("TRFD_ALERT_THRESHOLD", "3"))


def check(conn, threshold=None):
    limit = threshold or THRESHOLD
    rows = conn.execute(
        "SELECT route, COUNT(*) AS negative FROM feedback"
        " WHERE sentiment = 'negative' AND route IS NOT NULL"
        " GROUP BY route HAVING COUNT(*) >= ? ORDER BY negative DESC", (limit,))
    return [dict(r) for r in rows]
