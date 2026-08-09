import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import "../assets/web/js/application-data.js";

export const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const manifestPath = path.join(projectRoot, "assets/web/memweb/image-manifest.json");

const data = globalThis.MobileMemApplicationData;

if (!data) {
  throw new Error("MobileMemApplicationData did not initialize.");
}

const readJpegDimensions = (buffer, relativePath) => {
  const startOfFrameMarkers = new Set([
    0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf,
  ]);
  let offset = 2;

  while (offset + 8 < buffer.length) {
    if (buffer[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    const marker = buffer[offset + 1];
    offset += 2;
    if (marker === 0xd8 || marker === 0xd9) continue;

    const segmentLength = buffer.readUInt16BE(offset);
    if (startOfFrameMarkers.has(marker)) {
      return {
        width: buffer.readUInt16BE(offset + 5),
        height: buffer.readUInt16BE(offset + 3),
      };
    }
    offset += segmentLength;
  }

  throw new Error(`Could not read JPEG dimensions: ${relativePath}`);
};

const readWebpDimensions = (buffer, relativePath) => {
  let offset = 12;

  while (offset + 8 <= buffer.length) {
    const chunkType = buffer.subarray(offset, offset + 4).toString("ascii");
    const chunkSize = buffer.readUInt32LE(offset + 4);
    const dataOffset = offset + 8;

    if (chunkType === "VP8X" && dataOffset + 10 <= buffer.length) {
      return {
        width:
          1 +
          buffer[dataOffset + 4] +
          (buffer[dataOffset + 5] << 8) +
          (buffer[dataOffset + 6] << 16),
        height:
          1 +
          buffer[dataOffset + 7] +
          (buffer[dataOffset + 8] << 8) +
          (buffer[dataOffset + 9] << 16),
      };
    }

    if (chunkType === "VP8L" && dataOffset + 5 <= buffer.length) {
      const byte1 = buffer[dataOffset + 1];
      const byte2 = buffer[dataOffset + 2];
      const byte3 = buffer[dataOffset + 3];
      const byte4 = buffer[dataOffset + 4];
      return {
        width: 1 + byte1 + ((byte2 & 0x3f) << 8),
        height: 1 + (byte2 >> 6) + (byte3 << 2) + ((byte4 & 0x0f) << 10),
      };
    }

    if (chunkType === "VP8 " && dataOffset + 10 <= buffer.length) {
      return {
        width: buffer.readUInt16LE(dataOffset + 6) & 0x3fff,
        height: buffer.readUInt16LE(dataOffset + 8) & 0x3fff,
      };
    }

    offset = dataOffset + chunkSize + (chunkSize % 2);
  }

  throw new Error(`Could not read WebP dimensions: ${relativePath}`);
};

const readImageMetadata = (absolutePath) => {
  const buffer = fs.readFileSync(absolutePath);
  const signature = buffer.subarray(0, 8).toString("hex");
  const relativePath = path.relative(projectRoot, absolutePath);

  let format;
  let dimensions;
  if (signature === "89504e470d0a1a0a") {
    format = "image/png";
    dimensions = {
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  } else if (buffer[0] === 0xff && buffer[1] === 0xd8) {
    format = "image/jpeg";
    dimensions = readJpegDimensions(buffer, relativePath);
  } else if (
    buffer.subarray(0, 4).toString("ascii") === "RIFF" &&
    buffer.subarray(8, 12).toString("ascii") === "WEBP"
  ) {
    format = "image/webp";
    dimensions = readWebpDimensions(buffer, relativePath);
  } else {
    throw new Error(`Unsupported image format: ${relativePath}`);
  }

  return {
    format,
    ...dimensions,
    bytes: buffer.byteLength,
    sha256: crypto.createHash("sha256").update(buffer).digest("hex"),
  };
};

const labelFor = (uid, type, sampleIndex) => {
  if (type === "event") return data.eventLabels[uid]?.[sampleIndex] || null;
  if (["person", "group_chat_members"].includes(type)) {
    return data.identityLabels[uid]?.[type]?.[sampleIndex] || null;
  }
  return null;
};

export const buildImageManifest = () => {
  const records = data.users.flatMap((uid) =>
    data.categories.flatMap((type) =>
      Array.from({ length: data.previewCount }, (_, sampleIndex) => {
        const sampleNumber = sampleIndex + 1;
        const assetPath = data.resolveAssetPath(uid, type, sampleNumber);
        const absolutePath = path.join(projectRoot, assetPath);
        if (!fs.existsSync(absolutePath)) throw new Error(`Missing image: ${assetPath}`);

        return {
          uid,
          language: Number(uid.slice(3)) < 10 ? "zh" : "en",
          type,
          sampleNumber,
          label: labelFor(uid, type, sampleIndex),
          path: assetPath,
          ...readImageMetadata(absolutePath),
        };
      }),
    ),
  );

  return {
    version: 1,
    expectedCount: data.users.length * data.categories.length * data.previewCount,
    users: data.users,
    categories: data.categories,
    previewCount: data.previewCount,
    records,
  };
};

export const serializeManifest = (manifest) => `${JSON.stringify(manifest, null, 2)}\n`;
