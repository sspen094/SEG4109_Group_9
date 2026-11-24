import test from "node:test";
import assert from "node:assert/strict";
import { tagLocation } from "../src/location.js";

const location = {
  name: "Parliament Station",
  aliases: ["Parliament O-Train", "Parlement Station"],
};

test("tags a Reddit post that names a location alias", () => {
  const tag = tagLocation(
    { source: "reddit", title: "Delay at Parliament O-Train", text: "" },
    location,
  );
  assert.deepEqual(tag, { locationSpecific: true, locationMatch: "parliament o train" });
});

test("does not tag a generic Reddit post", () => {
  const tag = tagLocation(
    { source: "reddit", title: "Thoughts on the whole network?", text: "" },
    location,
  );
  assert.deepEqual(tag, { locationSpecific: false, locationMatch: null });
});

test("provider place IDs are location-specific", () => {
  assert.deepEqual(
    tagLocation({ source: "yelp", text: "Nice stop" }, location),
    { locationSpecific: true, locationMatch: "provider-place-id" },
  );
});
