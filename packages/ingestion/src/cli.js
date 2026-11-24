import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { loadEnvFile } from "node:process";
import { fileURLToPath } from "node:url";
import { ingestLocations } from "./ingest.js";
import { JsonlStore } from "./store.js";
import { DevvitRedditSource } from "./sources/devvit-reddit.js";
import { GoogleMapsSource } from "./sources/google-maps.js";
import { YelpSource } from "./sources/yelp.js";

const packageDirectory = resolve(fileURLToPath(new URL("..", import.meta.url)));
// npm runs workspace scripts with the package as cwd. INIT_CWD retains the
// directory where the user actually invoked npm (normally the repository root).
const invocationDirectory = process.env.INIT_CWD ?? process.cwd();
const configPath = resolve(invocationDirectory, process.argv[2] ?? "locations.json");
const outputPath = resolve(invocationDirectory, process.argv[3] ?? "data/reviews.jsonl");

// Load the repository's .env without an extra dependency. Values already set
// in the shell take precedence over values from the file.
try {
  loadEnvFile(resolve(invocationDirectory, ".env"));
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}

const locations = JSON.parse(await readFile(configPath, "utf8"));

const sources = [];
if (process.env.REDDIT_DEVVIT_ENDPOINT || process.env.REDDIT_DEVVIT_TOKEN) {
  sources.push(new DevvitRedditSource({
    endpoint: process.env.REDDIT_DEVVIT_ENDPOINT,
    token: process.env.REDDIT_DEVVIT_TOKEN,
  }));
}
if (process.env.YELP_API_KEY) {
  sources.push(new YelpSource({ apiKey: process.env.YELP_API_KEY }));
}
if (process.env.GOOGLE_MAPS_API_KEY) {
  sources.push(new GoogleMapsSource({ apiKey: process.env.GOOGLE_MAPS_API_KEY }));
}

if (!sources.length) {
  throw new Error(`No provider credentials found. See ${resolve(packageDirectory, "README.md")}`);
}

const summary = await ingestLocations({
  locations,
  sources,
  store: new JsonlStore(outputPath),
});
console.log(JSON.stringify(summary, null, 2));
if (summary.errors.length) process.exitCode = 1;
