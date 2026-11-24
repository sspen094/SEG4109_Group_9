import { getJson } from "../http.js";

export class YelpSource {
  name = "yelp";

  constructor({ apiKey, request = getJson }) {
    if (!apiKey) throw new Error("YELP_API_KEY is required for Yelp ingestion");
    this.apiKey = apiKey;
    this.request = request;
  }

  supports(location) {
    return Boolean(location.yelpBusinessId);
  }

  async fetchReviews(location) {
    const id = encodeURIComponent(location.yelpBusinessId);
    const result = await this.request(
      `https://api.yelp.com/v3/businesses/${id}/reviews`,
      { headers: { Authorization: `Bearer ${this.apiKey}` } },
    );

    return (result.reviews ?? []).map((review) => ({
      source: this.name,
      externalId: review.id ?? reviewIdFromUrl(review.url),
      title: "",
      text: review.text ?? "",
      rating: review.rating ?? null,
      author: review.user?.name ?? null,
      publishedAt: review.time_created
        ? new Date(review.time_created).toISOString()
        : null,
      sourceUrl: review.url ?? null,
    }));
  }
}

function reviewIdFromUrl(url) {
  if (!url) return null;
  try {
    return new URL(url).searchParams.get("hrid");
  } catch {
    return null;
  }
}
