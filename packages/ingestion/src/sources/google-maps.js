import { getJson } from "../http.js";

export class GoogleMapsSource {
  name = "google-maps";
  storageMode = "reference-only";

  constructor({ apiKey, request = getJson }) {
    if (!apiKey) throw new Error("GOOGLE_MAPS_API_KEY is required for Google Maps ingestion");
    this.apiKey = apiKey;
    this.request = request;
  }

  supports(location) {
    return Boolean(location.googlePlaceId);
  }

  async fetchReviews(location) {
    const placeId = encodeURIComponent(location.googlePlaceId);
    const result = await this.request(
      `https://places.googleapis.com/v1/places/${placeId}`,
      {
        headers: {
          "X-Goog-Api-Key": this.apiKey,
          "X-Goog-FieldMask": "id,reviews",
        },
      },
    );

    return (result.reviews ?? []).map((review) => ({
      source: this.name,
      externalId: review.name,
      title: "",
      text: review.text?.text ?? "",
      rating: review.rating ?? null,
      author: review.authorAttribution?.displayName ?? null,
      publishedAt: review.publishTime ?? null,
      sourceUrl: review.googleMapsUri ?? null,
      placeId: result.id ?? location.googlePlaceId,
    }));
  }

  toStoredRecord(review, location, collectedAt) {
    // Google permits storing place IDs, but not copied Places review content.
    // Keep the fetched review transient and persist only a collection marker.
    return {
      id: `google-maps:${location.id}:${review.placeId}`,
      recordType: "collection-reference",
      source: this.name,
      locationId: location.id,
      placeId: review.placeId,
      collectedAt,
      note: "Review content was not cached; fetch it from Places when needed.",
    };
  }
}
