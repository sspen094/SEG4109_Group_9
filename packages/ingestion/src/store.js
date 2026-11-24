import { appendFile, mkdir, readFile } from "node:fs/promises";
import { dirname } from "node:path";

export class JsonlStore {
  constructor(filePath) {
    this.filePath = filePath;
    this.ids = null;
  }

  async loadIds() {
    if (this.ids) return;
    this.ids = new Set();
    try {
      const content = await readFile(this.filePath, "utf8");
      for (const line of content.split("\n")) {
        if (line.trim()) this.ids.add(JSON.parse(line).id);
      }
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }

  async putMany(records) {
    await this.loadIds();
    const batchIds = new Set();
    const fresh = records.filter((record) => {
      if (this.ids.has(record.id) || batchIds.has(record.id)) return false;
      batchIds.add(record.id);
      return true;
    });
    if (!fresh.length) return 0;

    await mkdir(dirname(this.filePath), { recursive: true });
    await appendFile(
      this.filePath,
      `${fresh.map((record) => JSON.stringify(record)).join("\n")}\n`,
      "utf8",
    );
    fresh.forEach((record) => this.ids.add(record.id));
    return fresh.length;
  }
}
