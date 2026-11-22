"""Collection service: one connector per public feedback source.

The prototype runs in sample-data mode. Each connector reads its records from
data/sample_feedback.json instead of calling the live platform API, because
Reddit API approval is still pending and the course demo must run offline.
Live mode would read API keys from .env and call only the official APIs.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_FILE = DATA_DIR / "sample_feedback.json"


def _load_sample(source):
    with open(SAMPLE_FILE, encoding="utf-8") as f:
        return [r for r in json.load(f) if r["source"] == source]


def collect_reddit():
    """Posts and comments from r/ottawa and r/OCTranspo."""
    return _load_sample("reddit")


def collect_app_store():
    """Public reviews of the transit agency's mobile apps."""
    return _load_sample("app_store")


def collect_google_maps():
    """Public Google Maps reviews of O-Train stations."""
    return _load_sample("google_maps")


def collect_all():
    return collect_reddit() + collect_app_store() + collect_google_maps()
