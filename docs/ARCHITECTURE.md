# System Architecture

## 1. Architectural Style
- Pattern: Modular monolith with a pipes-and-filters processing pipeline, served through a layered web application (presentation, web/API, domain modules, data access).
- Rationale: The team is four part-time students with about 288 person-hours and free-tier hosting only. One deployable container is simpler to build, test and demo than separate services. The nightly batch work (collect, clean, score, tag) is a fixed sequence of independent steps, which is what pipes and filters suits: each filter can be tested alone and swapped (for example, replacing the lexicon sentiment baseline with a trained model) without changing the others. Module boundaries match the WBS deliverables (1.5 collection, 1.6 sentiment, 1.7 tagging, 1.8 dashboard), so a module can be split into its own service later if load requires it.

## 2. Component Interaction Diagram (Mermaid)
```mermaid
flowchart LR
    subgraph Sources["Public sources"]
        R["Reddit<br/>(Devvit app)"]
        AS["App Store<br/>reviews RSS"]
        GM["Google Places"]
    end
    GTFS["GTFS routes and stops"]
    SCH["Nightly scheduler<br/>scheduler.py"]
    R --> ING["Ingestion package<br/>packages/ingestion (Node.js)"]
    AS --> ING
    GM --> ING
    SCH -- "1. runs" --> ING
    ING --> J[("reviews.jsonl")]
    J --> C["Collection service<br/>collectors.py"]
    SAMPLE[("Sample dataset")] -. "fallback per source" .-> C
    SCH -- "2. runs" --> C
    C --> P["Pipeline filters<br/>normalize, dedupe,<br/>relevance, PII scrub<br/>pipeline.py"]
    P --> S["Sentiment engine<br/>sentiment.py"]
    S --> T["Tagging module<br/>tagging.py"]
    GTFS --> T
    T --> DB[("SQLite<br/>store.py")]
    DB --> AL["Alerting<br/>alerts.py"]
    DB --> W["Web / API layer<br/>app.py"]
    AL --> W
    W --> U["Staff browser<br/>dashboard and JSON"]
    U -- "sign in, overrides,<br/>admin settings" --> W
```

## 3. Data Flow & Execution Lifecycle
1. Ingestion: The nightly scheduler (in the app when `TRFD_SCHEDULER=1`, or `python -m trfd.scheduler --once` from Task Scheduler) runs at 02:00 and must finish before 06:00 (TR8). It first runs the Node.js ingestion package, which calls each source's official API or public feed and appends new records, without reviewer names, to `data/reviews.jsonl`. The collection service then reads that file; a source with no live records is replaced by the sample dataset (scope exclusion 10). The app also runs a pipeline-only cycle when it starts, and an administrator can start a full cycle from the Admin page.
2. Processing: Records are normalized into one format that keeps only text, timestamp and source (author fields are dropped). Cross-source duplicates are removed by a text fingerprint, off-topic Reddit posts are discarded, and usernames, emails and phone numbers are replaced with placeholders. The sentiment engine adds a label and confidence score, and the tagging module adds route, stop and issue category. Items with no resolvable route or stop are flagged for the manual tagging queue instead of being guessed.
3. Persistence & Response: New records are added to SQLite; items already stored (same text fingerprint) are skipped, so staff corrections survive later cycles. Each cycle is logged in the `runs` table. The alerting module checks negative volume per route against the threshold and window set by an administrator. The Flask layer checks the user's role, then answers dashboard and API requests with filtered queries and aggregates. Staff overrides update the record and are written to `override_log` with the old value and the staff member's username, so they can be used for retraining.

## 4. Architecture Decision Records (ADRs)
- ADR-01 (Modular monolith in one container): Context: small part-time team, fixed course deadlines, free-tier hosting. Chosen: one Flask application with separate modules per WBS deliverable. Trade-off accepted: modules cannot be scaled or deployed independently, and one failing module can stop the whole app.
- ADR-02 (SQLite for the prototype): Context: zero setup is needed for the demo and the data volume is small. Chosen: SQLite file inside the container. Trade-off accepted: single writer, and data is lost when the container is removed unless a volume is mounted. PostgreSQL is the planned replacement for deployment.
- ADR-03 (Lexicon baseline before a trained model): Context: the 500-item validation set is labelled by the team and no training data exists at the start of construction. Chosen: an explainable lexicon classifier with negation and sarcasm rules behind a single `score()` function. Trade-off accepted: lower accuracy on slang; if it misses the 80% agreement target it is replaced by a trained model behind the same interface.
- ADR-04 (Official APIs only, sample data per source as a fallback): Context: Reddit API access needs approval, Google's terms forbid storing Places review text, and Google Maps returns at most five reviews per place. Chosen: connectors use only official APIs and public feeds within published rate limits; any source without live records is shown on the synthetic sample file. Trade-off accepted: until access is granted, the demo shows live data only for the App Store.
- ADR-05 (Scrub personal data before storage): Context: the dashboard is seen by agency staff and the scope statement requires that usernames, handles and contact details never be stored. Chosen: PII scrubbing runs in the pipeline before any write. Trade-off accepted: a removed handle cannot be recovered to follow up with a rider.
- ADR-06 (Manual queue for unresolved locations): Context: vague feedback ("the bus at the downtown station") cannot be tied to a route reliably. Chosen: route and stop resolution against GTFS, with unresolved items flagged for staff tagging. Trade-off accepted: extra manual work for customer service staff.
- ADR-07 (Node.js ingestion hands off to the Python pipeline through a JSONL file): Context: the source adapters were built as a Node.js package and the pipeline and dashboard in Python. Chosen: the ingestion package appends normalized records to `data/reviews.jsonl` and the scheduler runs it before each pipeline cycle. Trade-off accepted: two runtimes to install, and the JSONL file holds raw text until the pipeline scrubs it, so it is kept out of Git and the Docker build context.
- ADR-08 (Session sign-in with three roles): Context: TR6 needs read-only executives, staff who correct tags, and administrators. Chosen: Flask session sign-in, Werkzeug password hashes, a role check on every page and API route, and one demo account per role on a new database. Trade-off accepted: no single sign-on with agency accounts (scope exclusion 9).
