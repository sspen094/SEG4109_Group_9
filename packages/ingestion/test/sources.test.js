import test from "node:test";
import assert from "node:assert/strict";
import { DevvitRedditSource } from "../src/sources/devvit-reddit.js";
import { YelpSource } from "../src/sources/yelp.js";

test("collects Reddit posts through the Devvit bridge", async () => {
  let receivedOptions;
  const source = new DevvitRedditSource({
    endpoint: "https://collector.example/external/reviews/search",
    token: "devvit_at_test",
    request: async (_url, options) => {
      receivedOptions = options;
      return {
        posts: [{
          id: "t3_abc",
          title: "Parliament Station",
          body: "Clean platform",
          author: "rider",
          createdAt: "2026-11-01T12:00:00.000Z",
          permalink: "/r/ottawa/comments/abc/review/",
        }],
      };
    },
  });

  const [review] = await source.fetchReviews({
    reddit: { query: "Parliament Station", subreddit: "ottawa", limit: 10 },
  });

  assert.equal(receivedOptions.headers.Authorization, "Bearer devvit_at_test");
  assert.deepEqual(JSON.parse(receivedOptions.body), {
    query: "Parliament Station",
    subreddit: "ottawa",
    limit: 10,
  });
  assert.equal(review.externalId, "t3_abc");
  assert.equal(review.sourceUrl, "https://www.reddit.com/r/ottawa/comments/abc/review/");
});

test("uses Yelp's hrid URL parameter when the response omits an id", async () => {
  const source = new YelpSource({
    apiKey: "test-key",
    request: async () => ({
      reviews: [{
        url: "https://www.yelp.com/biz/a-station?hrid=review-123",
        text: "Useful station",
        rating: 4,
        user: { name: "Rider" },
      }],
    }),
  });

  const [review] = await source.fetchReviews({ yelpBusinessId: "station" });
  assert.equal(review.externalId, "review-123");
});
