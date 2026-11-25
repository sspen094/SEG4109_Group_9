import { getJson } from "../http.js";

// Apple's public customer-reviews RSS feed (JSON format). It needs no API key
// and returns up to 50 of the most recent reviews per page, 10 pages at most.
// The reviewer's nickname is not collected (TR9).
export class AppStoreSource {
  name = "app-store";

  constructor({ request = getJson } = {}) {
    this.request = request;
  }

  supports(location) {
    return /^\d+$/.test(String(location.appStore?.appId ?? ""));
  }

  async fetchReviews(location) {
    const { appId, country = "ca", pages = 1 } = location.appStore;
    const pageCount = Math.min(Math.max(Math.trunc(pages), 1), 10);
    const reviews = [];

    for (let page = 1; page <= pageCount; page += 1) {
      // Apple's JSON feed has returned no entries for "/page=1/" URLs while the
      // same URL without a page number works, so page 1 omits it.
      const pagePart = page === 1 ? "" : `/page=${page}`;
      const result = await this.request(
        `https://itunes.apple.com/${encodeURIComponent(country)}/rss/customerreviews`
          + `${pagePart}/id=${encodeURIComponent(appId)}/sortby=mostrecent/json`,
      );
      // A feed with one entry returns an object instead of an array, and older
      // feeds put the app's own metadata first, without a rating.
      const entries = [].concat(result.feed?.entry ?? [])
        .filter((entry) => entry["im:rating"] && entry.content?.label);
      if (!entries.length) break;

      reviews.push(...entries.map((entry) => ({
        source: this.name,
        externalId: entry.id?.label ?? null,
        title: entry.title?.label ?? "",
        text: entry.content.label,
        rating: Number(entry["im:rating"].label),
        author: null,
        publishedAt: entry.updated?.label
          ? new Date(entry.updated.label).toISOString()
          : null,
        sourceUrl: `https://apps.apple.com/${country}/app/id${appId}`,
      })));
    }

    return reviews;
  }
}
