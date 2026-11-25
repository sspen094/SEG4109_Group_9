# Ottawa Transport Review System

A system for collecting public feedback about transit stations and stops,
classifying sentiment, and publishing reports.

The root Python app is the TRFD pipeline and dashboard. The Node.js ingestion
work is in package folders and feeds the pipeline:

- [`packages/ingestion`](packages/ingestion/README.md) collects feedback from
  Reddit (through the Devvit app), App Store reviews and Google Places, and
  appends it to `data/reviews.jsonl`.
- [`packages/reddit-devvit`](packages/reddit-devvit/README.md) is the
  Reddit-hosted collector used by the ingestion package.

## Run the dashboard

Needs Python 3.12 or newer. From the repository root (PowerShell or Command
Prompt; on macOS or Linux use `.venv/bin/python`):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Open <http://localhost:5000> and sign in with a demo account: `executive`
(read-only), `staff` (can correct sentiment and tags) or `admin` (also manages
sources, alert thresholds and users). The password for all three is
`trfd-demo`; set `TRFD_DEMO_PASSWORD` before the first run to change it.

On startup the app runs one pipeline cycle. Sources with records in
`data/reviews.jsonl` show live data; the others use the anonymized sample
dataset in `data/sample_feedback.json` (scope exclusion 10).

## Collect live feedback

Needs Node.js 20.12 or newer. The App Store feed needs no credentials; Reddit,
Yelp and Google need the keys described in the ingestion README.

```powershell
.venv\Scripts\python -m trfd.scheduler --once
```

This runs the Node ingestion package with `packages/ingestion/locations.json`
(or the example file if that does not exist), then the pipeline. The same cycle
can be started from the Admin page. To run it every night at 02:00, start the
app with `$env:TRFD_SCHEDULER = "1"`, or schedule the command above in Windows
Task Scheduler.

## Run in Docker

```powershell
docker build -t trfd-dashboard .
docker run --rm -p 8080:5000 -v trfd-state:/app/state trfd-dashboard
```

The image includes Node.js and runs the nightly cycle at 02:00 Ottawa time.
The `trfd-state` volume keeps the database and collected feedback.

## Route and station data

`data/routes.csv` and `data/stops.csv` list every OC Transpo route (all bus
routes and O-Train Lines 1, 2 and 4) and all stations with their coordinates.
They are built from OC Transpo's public GTFS Schedule feed, which OC Transpo
replaces about once a month. To refresh them:

```powershell
python -m trfd.gtfs
```

Nicknames already in the `aliases` column (such as "Tunney's") are kept. The
next collection cycle re-tags stored feedback, except items staff have
corrected. Street-corner bus stops are not loaded; feedback about them is
tagged by route.

Route and station data: OC Transpo GTFS Schedule feed
(<https://www.octranspo.com/en/plan-your-trip/travel-tools/developers>), used
under OC Transpo's developer terms.

## Settings

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `PORT` | `5000` | Web server port |
| `TRFD_DB` | `trfd.db` | SQLite database file |
| `TRFD_REVIEWS_FILE` | `data/reviews.jsonl` | Output of the ingestion package |
| `TRFD_SCHEDULER` | off | `1` runs the nightly cycle inside the app |
| `TRFD_RUN_AT` | `02:00` | Local time of the nightly cycle |
| `TRFD_INGEST_CONFIG` | `packages/ingestion/locations.json` | Locations file for ingestion |
| `TRFD_HISTORY_DAYS` | `365` | Oldest live feedback kept (scope exclusion 6) |
| `TRFD_ALERT_THRESHOLD` | `3` | Starting alert threshold (then set on the Admin page) |
| `TRFD_SECRET_KEY` | random | Session signing key; set it to keep sign-ins across restarts |
| `TRFD_DEMO_PASSWORD` | `trfd-demo` | Password for the demo accounts on a new database |

## Tests

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
npm test
```

## Documentation

- [Software Components](docs/COMPONENTS.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Development Methodology](docs/METHODOLOGY.md)
