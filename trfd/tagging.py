"""Tagging module: route, stop and issue category for each feedback item.

Routes and stations are resolved against data/routes.csv and data/stops.csv,
which trfd/gtfs.py builds from OC Transpo's published GTFS feed (every bus
route, O-Train Lines 1, 2 and 4, and every station), including colloquial
names ("the 88", "Tunney's", "Trillium Line"). Items with no route or
station that can be resolved are flagged for the manual tagging queue
instead of being guessed.
"""
import csv
import hashlib
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ISSUE_KEYWORDS = {
    "delays": {"late", "delay", "delayed", "wait", "waited", "waiting", "cancelled",
               "canceled", "ghost", "missed", "stuck", "schedule", "minutes"},
    "cleanliness": {"dirty", "filthy", "clean", "smells", "smell", "garbage", "trash"},
    "safety": {"unsafe", "safe", "safety", "scary", "fight", "harassed", "security"},
    "driver_conduct": {"driver", "operator", "rude", "polite", "friendly"},
    "accessibility": {"wheelchair", "elevator", "escalator", "ramp", "stroller",
                      "accessible", "accessibility", "stairs"},
    "fares": {"fare", "fares", "presto", "price", "expensive", "ticket", "pass"},
    "app_quality": {"app", "crashes", "crash", "login", "planner", "tracking", "update"},
}

# Categories that apply to the whole network, so no route or stop is expected.
SYSTEM_WIDE = {"app_quality", "fares"}

# A number after "route", "bus", "the" or "line", or before "bus", unless it is
# a time, a quantity or a duration ("the 20 minute wait", "the 7:15 bus").
UNITS = (r"min|mins|minutes?|hrs?|hours?|secs?|seconds?|am|pm|a\.m|p\.m|times?|people|"
         r"persons?|days?|weeks?|months?|years?|kms?|kilometres?|kilometers?|stops?|"
         r"buses|trains|cars|dollars?|bucks|cents?|percent")
NOT_A_ROUTE = rf"(?![:.,]\d)(?!\s*%)(?!\s*(?:{UNITS})\b)"
ROUTE_NUMBER = re.compile(
    rf"(?:\b(?:route|bus|the|line)\s+#?|#)(\d{{1,3}})\b{NOT_A_ROUTE}"
    rf"|(?<![:.,\d])\b(\d{{1,3}})\s+bus\b", re.I)


def _read_csv(name):
    with open(DATA_DIR / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


ROUTES = _read_csv("routes.csv")
STOPS = _read_csv("stops.csv")
# Changes when the route or station lists change, so stored tags can be refreshed.
REFERENCE_VERSION = hashlib.sha256(
    (DATA_DIR / "routes.csv").read_bytes() + (DATA_DIR / "stops.csv").read_bytes()
).hexdigest()[:12]
ROUTE_IDS = {r["route_id"] for r in ROUTES}
ROUTE_NAMES = {r["route_id"]: r["name"] for r in ROUTES}
ROUTE_DESCRIPTIONS = {r["route_id"]: r.get("description") or "" for r in ROUTES}
STOP_NAMES = [s["stop_name"] for s in STOPS]
CATEGORIES = tuple(ISSUE_KEYWORDS) + ("other",)


def _alias_pattern(aliases):
    parts = [re.escape(a.strip()) for a in aliases.split("|") if a.strip()]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.I)


ROUTE_ALIASES = [(r["route_id"], _alias_pattern(r["aliases"])) for r in ROUTES if r["aliases"]]
STOP_ALIASES = [(s["stop_name"], _alias_pattern(s["aliases"])) for s in STOPS if s["aliases"]]
STOP_ROUTE = {s["stop_name"]: s["route_id"] or None for s in STOPS}


def _plain_quotes(text):
    return (text or "").replace("’", "'").replace("‘", "'")


def resolve_route(text):
    text = _plain_quotes(text)
    for route_id, pattern in ROUTE_ALIASES:
        if pattern.search(text):
            return route_id
    for match in ROUTE_NUMBER.finditer(text):
        number = match.group(1) or match.group(2)
        if number in ROUTE_IDS:
            return number
    return None


def resolve_stop(text):
    text = _plain_quotes(text)
    for stop_name, pattern in STOP_ALIASES:
        if pattern.search(text):
            return stop_name
    return None


def classify_issue(text):
    words = set(re.findall(r"[a-z]+", text.lower()))
    counts = {cat: len(words & kws) for cat, kws in ISSUE_KEYWORDS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] else "other"


def tag(text, hint=None, source=None):
    """hint: the location a collector searched for (for example the station a
    Reddit query or place review belongs to), used when the text names none."""
    stop = resolve_stop(text) or (resolve_stop(hint) if hint else None)
    # No route named: fall back to the line serving the station, if any.
    route = resolve_route(text) or STOP_ROUTE.get(stop)
    category = classify_issue(text)
    if category == "other" and source == "app_store":
        category = "app_quality"  # an app review with no other issue is about the app
    return {
        "route": route,
        "stop": stop,
        "category": category,
        "needs_review": route is None and stop is None and category not in SYSTEM_WIDE,
    }
