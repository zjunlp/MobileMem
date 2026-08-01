import fs from "node:fs";

import { buildImageManifest, manifestPath, serializeManifest } from "./image-manifest.mjs";

const expected = buildImageManifest();
const actualText = fs.readFileSync(manifestPath, "utf8");
const expectedText = serializeManifest(expected);

if (actualText !== expectedText) {
  throw new Error("Image manifest is stale. Run `npm run images:build` and review the diff.");
}

if (expected.records.length !== expected.expectedCount || expected.expectedCount !== 360) {
  throw new Error(`Expected 360 image records, found ${expected.records.length}.`);
}

for (const uid of expected.users) {
  const userRecords = expected.records.filter((record) => record.uid === uid);
  if (userRecords.length !== 60)
    throw new Error(`${uid} has ${userRecords.length} records, not 60.`);

  for (const type of expected.categories) {
    const categoryRecords = userRecords.filter((record) => record.type === type);
    if (categoryRecords.length !== expected.previewCount) {
      throw new Error(`${uid}/${type} has ${categoryRecords.length} records, not 5.`);
    }
    if (new Set(categoryRecords.map((record) => record.sha256)).size !== categoryRecords.length) {
      throw new Error(`${uid}/${type} contains duplicate image files.`);
    }
  }
}

for (const record of expected.records) {
  if (record.width <= 0 || record.height <= 0 || record.bytes <= 0) {
    throw new Error(`Invalid image metadata: ${record.path}`);
  }
  if (["event", "person", "group_chat_members"].includes(record.type) && !record.label) {
    throw new Error(`Missing display label: ${record.path}`);
  }
}

console.log(`Verified ${expected.records.length} curated image records.`);
