# Software Components

Transit Rider Feedback Dashboard (TRFD), SEG4105 Group 9. The prototype is a Python 3.12 / Flask application. It runs on synthetic sample data, so the connectors read `data/sample_feedback.json` instead of calling the live platform APIs.

## 1. Component Inventory
| Component / Module | Directory / File Path | Primary Responsibility | Key Dependencies |
| :--- | :--- | :--- | :--- |
| Presentation / UI (dashboard) | /templates/index.html | Summary counts, alerts, hotspot table, filterable feedback table, manual tagging queue filter | Jinja2 (bundled with Flask) |
| Web / API layer | /app.py | HTTP routes for the dashboard and JSON API, query-string filters, staff overrides, startup collection cycle | Flask 3.1 |
| Collection service | /trfd/collectors.py | One connector per public source (Reddit, App Store reviews, Google Maps station reviews) returning raw records | Sample data file (live mode: official platform APIs, keys in .env) |
| Processing pipeline | /trfd/pipeline.py | Normalizes records, removes cross-source duplicates, filters off-topic Reddit posts, scrubs usernames, emails and phone numbers, runs a full cycle | sentiment, tagging, store, alerts modules; Python re, hashlib |
| Sentiment engine | /trfd/sentiment.py | Labels each item negative, neutral or positive with a confidence score; handles negation and sarcasm cues | Python standard library (lexicon baseline) |
| Tagging module | /trfd/tagging.py | Resolves route and stop from free text, including colloquial names; assigns issue category; flags unresolved items for manual tagging | GTFS reference data in /data/routes.csv and /data/stops.csv |
| Data access / storage | /trfd/store.py | SQLite schema, inserts, filtered queries, hotspot and summary aggregates, override log | sqlite3 (standard library) |
| Alerting | /trfd/alerts.py | Raises an alert when negative volume for a route reaches the threshold (TRFD_ALERT_THRESHOLD, default 3) | store (SQLite) |
| Reference and sample data | /data/ | Synthetic feedback records and the demo subset of GTFS routes and stops | None |
| Tests | /tests/test_trfd.py | Unit tests for each module and integration tests for the full cycle and API | pytest, pytest-cov |
| Container build | /Dockerfile, /.dockerignore | Builds the runnable image published to Docker Hub | python:3.12-slim base image |

## 2. External Interfaces & APIs
- Input Interfaces:
  - Source connectors: Reddit API, App Store reviews, Google Maps Places reviews (sample-data mode in the prototype).
  - GTFS reference data (routes and stops) loaded from `/data`.
  - CLI: `python -m trfd.pipeline` runs one collection cycle (scheduled nightly in deployment).
  - REST: `POST /api/feedback/<id>/override` with a JSON body such as `{"route": "97", "category": "delays"}`.
  - Query strings on `/` and `/api/feedback`: `source`, `sentiment`, `route`, `category`, `needs_review=1`.
  - Environment variables: `PORT` (default 5000), `TRFD_DB` (default trfd.db), `TRFD_ALERT_THRESHOLD` (default 3).
- Output Interfaces:
  - HTML dashboard at `/`.
  - JSON: `GET /api/feedback`, `GET /api/hotspots` (hotspots and active alerts), `GET /health`.
  - Database writes to the `feedback` and `override_log` tables.
  - Console log of each collection cycle and the alerts it raised.
