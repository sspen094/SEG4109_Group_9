import test from "node:test";
import assert from "node:assert/strict";
import { AppStoreSource } from "../src/sources/app-store.js";
import { DevvitRedditSource } from "../src/sources/devvit-reddit.js";
import { YelpSource } from "../src/sources/yelp.js";

test("collects App Store reviews from the public RSS feed without reviewer names", async () => {
  const urls = [];
  const source = new AppStoreSource({
    request: async (url) => {
      urls.push(url);
      if (url.includes("/page=2/")) return { feed: {} };
      return {
        feed: {
          entry: [
            { "im:name": { label: "App metadata entry" } },
            {
              id: { label: "14704526375" },
              author: { name: { label: "SomeRider" } },
              title: { label: "Travel planner" },
              content: { label: "No delay alerts in the app" },
              "im:rating": { label: "1" },
              updated: { label: "2026-10-24T01:23:36-07:00" },
            },
          ],
        },
      };
    },
  });

  const location = { appStore: { appId: "1436639405", country: "ca", pages: 3 } };
  assert.equal(source.supports(location), true);
  assert.equal(source.supports({ appStore: { appId: "replace-me" } }), false);

  const reviews = await source.fetchReviews(location);
  assert.equal(urls.length, 2); // stops at the first empty page
  assert.match(urls[0], /itunes\.apple\.com\/ca\/rss\/customerreviews\/id=1436639405\//);
  assert.match(urls[1], /\/customerreviews\/page=2\/id=1436639405\//);
  assert.equal(reviews.length, 1);
  assert.equal(reviews[0].externalId, "14704526375");
  assert.equal(reviews[0].rating, 1);
  assert.equal(reviews[0].author, null);
  assert.equal(reviews[0].publishedAt, "2026-10-24T08:23:36.000Z");
});

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
