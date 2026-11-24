import { getJson } from "../http.js";

export class DevvitRedditSource {
  name = "reddit";

  constructor({ endpoint, token, request = getJson }) {
    if (!endpoint) throw new Error("REDDIT_DEVVIT_ENDPOINT is required for Reddit ingestion");
    if (!token) throw new Error("REDDIT_DEVVIT_TOKEN is required for Reddit ingestion");
    this.endpoint = endpoint;
    this.token = token;
    this.request = request;
  }

  supports(location) {
    return Boolean(location.reddit?.query);
  }

  async fetchReviews(location) {
    const result = await this.request(this.endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: location.reddit.query,
        subreddit: location.reddit.subreddit ?? "all",
        limit: location.reddit.limit ?? 25,
      }),
    });

    return (result.posts ?? []).map((post) => ({
      source: this.name,
      externalId: post.id,
      title: post.title ?? "",
      text: post.body ?? "",
      rating: null,
      author: post.author ?? null,
      publishedAt: post.createdAt ?? null,
      sourceUrl: post.permalink
        ? new URL(post.permalink, "https://www.reddit.com").toString()
        : null,
    }));
  }
}
