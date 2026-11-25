import { createHash } from "node:crypto";
import { tagLocation } from "./location.js";

function recordId(review) {
  if (review.externalId) return `${review.source}:${review.externalId}`;
  const identity = [review.sourceUrl, review.author, review.publishedAt, review.text].join("|");
  const fallback = createHash("sha256").update(identity).digest("hex");
  return `${review.source}:${fallback}`;
}

function toStoredRecord(review, location, collectedAt) {
  return {
    id: recordId(review),
    recordType: "review",
    source: review.source,
    externalId: review.externalId,
    locationId: location.id,
    locationName: location.name,
    ...tagLocation(review, location),
    title: review.title,
    text: review.text,
    rating: review.rating,
    // Reviewer names are never stored (TR9); author only feeds the fallback ID hash.
    publishedAt: review.publishedAt,
    sourceUrl: review.sourceUrl,
    collectedAt,
  };
}

export async function ingestLocations({ locations, sources, store, logger = console }) {
  const summary = { fetched: 0, stored: 0, errors: [] };

  for (const location of locations) {
    for (const source of sources) {
      if (!source.supports(location)) continue;
      try {
        const reviews = await source.fetchReviews(location);
        const collectedAt = new Date().toISOString();
        const records = reviews.map((review) =>
          source.toStoredRecord
            ? source.toStoredRecord(review, location, collectedAt)
            : toStoredRecord(review, location, collectedAt),
        );
        summary.fetched += reviews.length;
        summary.stored += await store.putMany(records);
      } catch (error) {
        const failure = { locationId: location.id, source: source.name, message: error.message };
        summary.errors.push(failure);
        logger.error(`[${source.name}] ${location.name}: ${error.message}`);
      }
    }
  }

  return summary;
}
