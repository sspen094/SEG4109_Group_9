import { serve } from "@hono/node-server";
import { createServer, getServerPort, reddit } from "@devvit/web/server";
import { Hono } from "hono";

type SearchRequest = {
  query?: string;
  subreddit?: string;
  limit?: number;
};

const app = new Hono();

app.post("/external/reviews/search", async (context) => {
  const input = await context.req.json<SearchRequest>();
  const query = input.query?.trim();
  const subreddit = input.subreddit?.trim() || "all";
  const limit = Math.min(Math.max(Math.trunc(input.limit ?? 25), 1), 100);

  if (!query) {
    return context.json({ error: "query is required" }, 400);
  }

  const listing = reddit.searchPosts({
    query,
    subredditName: subreddit === "all" ? undefined : subreddit,
    sort: "new",
    timeframe: "all",
    limit,
  });

  const posts = [];
  for await (const post of listing) {
    posts.push({
      id: post.id,
      title: post.title,
      body: post.body ?? "",
      author: post.authorName,
      createdAt: post.createdAt.toISOString(),
      permalink: post.permalink,
    });
    if (posts.length >= limit) break;
  }

  return context.json({ posts });
});

serve({
  fetch: app.fetch,
  createServer,
  port: getServerPort(),
});
