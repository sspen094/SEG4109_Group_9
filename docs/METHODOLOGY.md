# Development Methodology

## 1. Software Development Lifecycle (SDLC)
- Framework: Hybrid. A plan-driven, phase-gate lifecycle covers project definition, requirements and design (milestones M1 to M3, Sep 14 to Nov 5, 2026). Construction then runs as two planned increments of one-week, Scrum-style sprints: Increment 1 (Nov 6 to 19) builds the data pipeline (M4), and Increment 2 (Nov 20 to Dec 3) builds the dashboard views, alerting and end-to-end integration (M5). Closure follows (M6, Dec 5). At each milestone gate the instructor, acting as sponsor, reviews the deliverables and decides go, recycle or kill.
- Planning & Tracking: Work items are logged as GitHub Issues and prioritized in Project Boards. The baseline WBS and schedule are kept in OpenProject; each sprint pulls its work packages from that baseline into GitHub Issues.

## 2. Version Control & Branching Strategy
- Workflow: GitHub Flow.
- main: Always contains production-ready, tested code.
- feature/* | fix/* | docs/*: Short-lived branches created from main for isolated changes.
- Commit Convention: Conventional Commits (feat:, fix:, docs:, refactor:, test:, chore:).
- Pull requests reference their issue with "Closes #n" so the issue closes on merge, and need one approving review from another group member.

## 3. Code Review & Definition of Done (DoD)
1. Code compiles/runs locally without errors or regressions.
2. Unit and integration tests pass.
3. Relevant documentation (README and /docs) is updated.
4. Changes are submitted via Pull Request and reviewed prior to merging into main.
5. No usernames, handles or contact details can reach the database, and new UI follows WCAG 2.1 Level AA.

## 4. Testing & Quality Assurance Strategy
- Unit Testing: pytest, with tests in `/tests`. Target: at least 80% line coverage of the `trfd` package and `app.py`, measured with pytest-cov (`python -m pytest --cov=trfd --cov=app`). Static analysis with flake8 runs before each pull request.
- Integration / System Testing: Integration tests run a full collection cycle on the sample data and call every endpoint through the Flask test client. System acceptance checks against the scope statement: at least 80% sentiment agreement with the 500-item team-labelled validation set, dashboard pages under 3 seconds with 12 months of data, the nightly cycle finishing before 06:00, five consecutive unattended daily cycles, and a WCAG 2.1 AA accessibility review. The Docker image is built and run before each release.
