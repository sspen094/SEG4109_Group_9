import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { JsonlStore } from "../src/store.js";

test("deduplicates records within and across runs", async (context) => {
  const directory = await mkdtemp(join(tmpdir(), "otrs-ingestion-"));
  context.after(() => rm(directory, { recursive: true, force: true }));
  const file = join(directory, "reviews.jsonl");
  const store = new JsonlStore(file);

  assert.equal(await store.putMany([{ id: "one" }, { id: "one" }]), 1);
  assert.equal(await store.putMany([{ id: "one" }, { id: "two" }]), 1);

  const lines = (await readFile(file, "utf8")).trim().split("\n");
  assert.deepEqual(lines.map((line) => JSON.parse(line).id), ["one", "two"]);
});
