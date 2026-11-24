# Reddit Devvit collector

This small Reddit-hosted app owns Reddit authentication and exposes one protected
endpoint for the Node ingestion package. It uses Devvit's `reddit.searchPosts()`;
there are no legacy Reddit client IDs, secrets, or OAuth bearer tokens.

## Requirements

- Node.js 24 or newer (required by the current Devvit toolchain)
- A Devvit app created at <https://developers.reddit.com/new>
- Reddit approval for External Endpoints, which are currently limited-access

Replace the `name` in `devvit.json` with the app slug assigned by Reddit.

## Deploy

From the repository root:

```powershell
npm install
npm run login --workspace @otrs/reddit-devvit
npm run deploy --workspace @otrs/reddit-devvit
```

In the app's Developer Settings, create a managed App Token. It begins with
`devvit_at_` and is shown only once. Put the full deployed endpoint URL and that
token in the repository-root `.env`:

```dotenv
REDDIT_DEVVIT_ENDPOINT=https://APP-SLUG-SUBREDDIT-ID-external.devvit.net/external/reviews/search
REDDIT_DEVVIT_TOKEN=devvit_at_REPLACE_ME
```

Do not use the token saved by `devvit login`; that authenticates the CLI only.
Managed tokens are sent to the external endpoint as a Bearer token and should
remain only in `.env` or another server-side secret store.
