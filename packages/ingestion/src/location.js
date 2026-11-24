function searchable(text) {
  return String(text ?? "")
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toLowerCase();
}

export function tagLocation(review, location) {
  // A Yelp or Google place ID already points at one specific station or stop.
  if (review.source === "yelp" || review.source === "google-maps") {
    return { locationSpecific: true, locationMatch: "provider-place-id" };
  }

  const haystack = searchable(`${review.title ?? ""} ${review.text ?? ""}`);
  const aliases = [location.name, ...(location.aliases ?? [])]
    .map(searchable)
    .filter(Boolean);
  const matchedAlias = aliases.find((alias) => haystack.includes(alias));

  return matchedAlias
    ? { locationSpecific: true, locationMatch: matchedAlias }
    : { locationSpecific: false, locationMatch: null };
}
