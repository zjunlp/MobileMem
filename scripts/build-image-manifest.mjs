import fs from "node:fs";

import { buildImageManifest, manifestPath, serializeManifest } from "./image-manifest.mjs";

const manifest = buildImageManifest();
fs.writeFileSync(manifestPath, serializeManifest(manifest));
console.log(`Wrote ${manifest.records.length} image records to ${manifestPath}`);
