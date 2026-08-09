import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// Trajectory files store dataset paths that application-data.js resolves to curated assets at runtime.
const sourceFiles = [
  "index.html",
  "assets/web/css/application-browser.css",
  "assets/web/css/case-demo.css",
  "assets/web/css/site.css",
  "assets/web/js/application-browser.js",
  "assets/web/js/application-data.js",
  "assets/web/js/case-demo.js",
  "assets/web/js/main.js",
  "assets/web/js/quick-start.js",
];
const assetPattern = /assets\/[A-Za-z0-9_./-]+\.(?:css|gif|jpe?g|js|mp4|pdf|png|webp)/g;
const references = new Set();

for (const relativePath of sourceFiles) {
  const source = fs.readFileSync(path.join(projectRoot, relativePath), "utf8");
  source.match(assetPattern)?.forEach((assetPath) => references.add(assetPath));
}

const missing = [...references].filter(
  (relativePath) => !fs.existsSync(path.join(projectRoot, relativePath)),
);

if (missing.length) {
  throw new Error(`Missing static assets:\n${missing.map((item) => `- ${item}`).join("\n")}`);
}

console.log(`Verified ${references.size} literal static-asset references.`);
