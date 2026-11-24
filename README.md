# Ottawa Transport Review System

A system for collecting public feedback about transit stations and stops,
classifying sentiment, and publishing reports.

The root Python prototype provides the current TRFD pipeline and web interface.
The Node.js ingestion work is isolated in package folders:

- [`packages/ingestion`](packages/ingestion/README.md) normalizes feedback from
  Yelp, Google Places, and Reddit.
- [`packages/reddit-devvit`](packages/reddit-devvit/README.md) is the
  Reddit-hosted collector used by the ingestion package.

## Documentation

- [Software Components](docs/COMPONENTS.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Development Methodology](docs/METHODOLOGY.md)
