# Ingestion

Small provider adapters turn Reddit posts, App Store reviews and place reviews into
one record shape, tag location-specific records, and append new records to a
deduplicated JSONL file. The Python dashboard pipeline (`trfd/collectors.py`) reads
that file, and the nightly scheduler (`python -m trfd.scheduler`) runs this package
before each pipeline cycle. Reviewer names are not stored (TR9).

## Configure

Copy `locations.example.json` to a convenient path and replace the provider IDs.
Copy the example environment file from the repository root, then fill in the
credentials for the providers you want to run:

```powershell
Copy-Item .env.example .env
```

The ingestion command loads this `.env` automatically. Only providers with a
credential are run:

- `REDDIT_DEVVIT_ENDPOINT` and `REDDIT_DEVVIT_TOKEN`
- `YELP_API_KEY`
- `GOOGLE_MAPS_API_KEY`

App Store reviews need no credential. A location with an `appStore` block
(`appId`, `country`, `pages` up to 10) is collected from Apple's public customer
reviews RSS feed. OC Transpo has no official iOS app, so the example uses the
most-reviewed Ottawa transit app, "Ottawa Transit (OC Transpo)" (third party,
id 1436639405). Replace it if the group picks a different app.

Values already set in your terminal take precedence over `.env` values.

Reddit collection runs through the sibling `packages/reddit-devvit` app; a
Devvit CLI login token is not an API token and should not be placed in `.env`.
See that package's README for deployment and managed-token setup. Yelp's reviews
endpoint may require a paid plan.

## Run

From the repository root:

```powershell
npm run ingest -- packages/ingestion/locations.example.json data/reviews.jsonl
```

The output is newline-delimited JSON, so later sentiment and reporting packages can
stream it without knowing anything about provider response formats. Existing IDs are
not appended again.

Google Places review content is intentionally transient. Google's Places policies
permit storing place IDs but prohibit copying and saving user reviews. The Google
adapter therefore writes one `collection-reference` marker per place instead of
review text. A deployment with separately negotiated content rights should implement
its own storage policy after legal review.
