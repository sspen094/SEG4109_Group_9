import test from "node:test";
import assert from "node:assert/strict";
import { ingestLocations } from "../src/ingest.js";

test("normalizes, tags, and stores reviews", async () => {
  const written = [];
  const source = {
    name: "reddit",
    supports: () => true,
    fetchReviews: async () => [{
      source: "reddit",
      externalId: "abc",
      title: "Parliament Station was clean",
      text: "Easy trip",
      rating: null,
      author: "rider",
      publishedAt: "2026-01-01T00:00:00.000Z",
      sourceUrl: "https://www.reddit.com/r/ottawa/comments/abc",
    }],
  };
  const store = {
    putMany: async (records) => {
      written.push(...records);
      return records.length;
    },
  };

  const summary = await ingestLocations({
    locations: [{ id: "parliament", name: "Parliament Station" }],
    sources: [source],
    store,
  });

  assert.equal(summary.fetched, 1);
  assert.equal(summary.stored, 1);
  assert.equal(written[0].id, "reddit:abc");
  assert.equal(written[0].locationSpecific, true);
});

test("continues when one source fails", async () => {
  const summary = await ingestLocations({
    locations: [{ id: "parliament", name: "Parliament Station" }],
    sources: [{
      name: "reddit",
      supports: () => true,
      fetchReviews: async () => { throw new Error("rate limited"); },
    }],
    store: { putMany: async () => 0 },
    logger: { error: () => {} },
  });

  assert.equal(summary.errors.length, 1);
  assert.equal(summary.errors[0].message, "rate limited");
});
