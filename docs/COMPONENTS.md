# Software Components

Transit Rider Feedback Dashboard (TRFD), SEG4105 Group 9. The dashboard and processing pipeline are a Python 3.12 / Flask application. Collection from the live platforms is done by the Node.js ingestion package, which writes `data/reviews.jsonl` for the pipeline to read. Sources with no live records are demonstrated on the synthetic sample dataset in `data/sample_feedback.json` (scope exclusion 10).

## 1. Component Inventory
| Component / Module | Directory / File Path | Primary Responsibility | Key Dependencies |
| :--- | :--- | :--- | :--- |
| Presentation / UI (dashboard) | /templates/, /static/ | Sign-in page; overview with summary tiles, alerts, source status, stop hotspot map, sentiment charts and route hotspots; filterable feedback table; manual tagging queue; retagging screen with override history; admin page | Jinja2 (bundled with Flask), Chart.js 4.4.1 and Leaflet 1.9.4 from cdnjs (each figure also has a data table) |
| Web / API layer | /app.py | HTTP routes for the pages and JSON API, query-string filters, staff overrides, admin actions, CSRF tokens on forms, startup collection cycle | Flask 3.1 |
| Access control | /trfd/auth.py | Role checks for executive (read-only), staff (overrides) and admin (users, sources, thresholds) (TR6) | Flask sessions; passwords hashed with Werkzeug |
| Ingestion package (Node.js) | /packages/ingestion | Provider adapters for Reddit (through the Devvit app), App Store reviews (Apple's public RSS feed), Google Places and Yelp; normalizes records, drops reviewer names, appends new records to `data/reviews.jsonl` | Node.js 20.12+, no npm dependencies |
| Reddit collector (Devvit app) | /packages/reddit-devvit | Reddit-hosted app exposing one protected search endpoint for the ingestion package | Devvit 0.15, Hono; needs Reddit approval for External Endpoints |
| Collection service | /trfd/collectors.py | Reads the ingestion output for Reddit, App Store and Google Maps (Yelp is out of scope and ignored), keeps the last 12 months, and falls back to the sample dataset per source | ingestion output, sample data file |
| Processing pipeline | /trfd/pipeline.py | Normalizes records, removes cross-source duplicates, filters off-topic Reddit posts, scrubs usernames, emails and phone numbers, scores, tags, stores new items and logs each run | sentiment, tagging, store, alerts modules; Python re |
| Nightly scheduler | /trfd/scheduler.py | Runs the ingestion package and then the pipeline every night (default 02:00), retries with back-off, records each run | subprocess (Node.js), threading |
| Sentiment engine | /trfd/sentiment.py | Labels each item negative, neutral or positive with a confidence score; handles negation and sarcasm cues | Python standard library (lexicon baseline) |
| Tagging module | /trfd/tagging.py | Resolves route and stop from free text (including colloquial names) or the collector's location hint; assigns issue category; flags unresolved items for manual tagging | GTFS reference data in /data/routes.csv and /data/stops.csv (with stop coordinates) |
| Data access / storage | /trfd/store.py | SQLite schema and migration, incremental inserts by text fingerprint, filtered queries, aggregates for tiles, charts and map, override log, settings, users, run log | sqlite3 (standard library) |
| Alerting | /trfd/alerts.py | Raises an alert when negative volume for a route reaches the threshold within the alert window (both set on the Admin page) | store (SQLite) |
| Reference and sample data | /data/ | Synthetic feedback records and the demo subset of GTFS routes and stops | None |
| Tests | /tests/test_trfd.py, /packages/ingestion/test/ | Python unit and integration tests (pipeline, bridge, roles, forms, load time); Node tests for the adapters and store | pytest, pytest-cov, node:test |
| Container build | /Dockerfile, /.dockerignore | Builds the runnable image (Python app plus the Node.js binary for ingestion, nightly scheduler on) | python:3.12-slim and node:22-slim base images |

## 2. External Interfaces & APIs
- Input Interfaces:
  - Source connectors (ingestion package): Reddit through the Devvit endpoint, Apple's public App Store customer reviews RSS feed, Google Places API (place references only), Yelp Fusion API (outside the scope statement, not loaded by the pipeline).
  - GTFS reference data (routes and stops) loaded from `/data`.
  - CLI: `python -m trfd.pipeline` runs one pipeline cycle; `python -m trfd.scheduler --once` runs ingestion and then the pipeline; `python -m trfd.scheduler` runs it every night.
  - REST: `POST /api/feedback/<id>/override` (staff or admin) with a JSON body such as `{"route": "97", "category": "delays"}`.
  - Query strings on `/`, `/feedback` and `/api/feedback`: `source`, `sentiment`, `route`, `stop`, `category`, `needs_review=1`, `q` (text search), `days` (date range).
  - Forms: sign in, retag an item, admin settings, add or delete a user, run collection now.
  - Environment variables: listed in the README (`PORT`, `TRFD_DB`, `TRFD_REVIEWS_FILE`, `TRFD_SCHEDULER`, `TRFD_RUN_AT`, `TRFD_ALERT_THRESHOLD` and others).
- Output Interfaces:
  - HTML pages: `/` (overview), `/feedback`, `/feedback/<id>`, `/admin`, `/login`.
  - JSON: `GET /api/feedback`, `GET /api/hotspots` (route hotspots, stop counts with coordinates, active alerts), `GET /health`. All except `/health` need a signed-in user.
  - Database writes to the `feedback`, `override_log`, `settings`, `users` and `runs` tables.
  - `data/reviews.jsonl` written by the ingestion package (raw staging file, never committed).
  - Console log of each collection cycle and the alerts it raised.
