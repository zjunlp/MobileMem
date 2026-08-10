#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
CUSTOM_PYTHON_BIN="${PYTHON_BIN:-}"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/.cache/mobilemem-smoke}"
UUID="${UUID:-10}"
MAX_EVENTS="${MAX_EVENTS:-1}"
MAX_WORKERS="${MAX_WORKERS:-1}"

# Create the local environment only when it does not already exist.
if [[ ! -x "$PYTHON_BIN" ]]; then
  if [[ -n "$CUSTOM_PYTHON_BIN" ]]; then
    printf 'PYTHON_BIN is not executable: %s\n' "$PYTHON_BIN" >&2
    exit 1
  fi
  SYSTEM_PYTHON="$(command -v python3.11 || command -v python3 || true)"
  if [[ -z "$SYSTEM_PYTHON" ]] || ! "$SYSTEM_PYTHON" -c \
    'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    printf 'Python 3.11 or newer is required.\n' >&2
    exit 1
  fi
  printf 'Creating Python environment: %s\n' "$REPO_ROOT/.venv"
  "$SYSTEM_PYTHON" -m venv "$REPO_ROOT/.venv"
fi

if ! "$PYTHON_BIN" -c '
import bs4, cv2, dotenv, html2image, jsonlines, numpy, openai, playwright
import qrcode, requests, scipy, tenacity, tqdm
from PIL import Image
' >/dev/null 2>&1; then
  printf 'Installing Python dependencies...\n'
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install \
    -r "$REPO_ROOT/omni/requirements.txt" "html2image>=2,<3"
fi

ENV_FILE="$REPO_ROOT/omni/src/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$REPO_ROOT/omni/src/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf 'Created %s. Fill in the API settings, then run this script again.\n' \
    "$ENV_FILE" >&2
  exit 1
fi

# html2image needs the Chromium installed by Playwright on machines without Chrome.
playwright_chromium() {
  "$PYTHON_BIN" -c '
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
' 2>/dev/null
}

HTML2IMAGE_CHROME_BIN="${HTML2IMAGE_CHROME_BIN:-$(playwright_chromium)}"
if [[ ! -x "$HTML2IMAGE_CHROME_BIN" ]]; then
  printf 'Installing Playwright Chromium...\n'
  "$PYTHON_BIN" -m playwright install chromium
  HTML2IMAGE_CHROME_BIN="$(playwright_chromium)"
fi
export HTML2IMAGE_CHROME_BIN
export HTML2IMAGE_TOGGLE_ENV_VAR_LOOKUP=1

mkdir -p "$OUTPUT_ROOT/data" "$OUTPUT_ROOT/image"
OUTPUT_ROOT="$(cd "$OUTPUT_ROOT" && pwd -P)"

if [[ -s "$OUTPUT_ROOT/data/annual_events.jsonl" \
      && -s "$OUTPUT_ROOT/data/image_summaries.jsonl" \
      && -s "$OUTPUT_ROOT/data/total_images.jsonl" ]] \
    && find "$OUTPUT_ROOT/image" -type f -name '*.png' -print -quit | grep -q .; then
  printf 'Trajectory already complete: %s\n' "$OUTPUT_ROOT"
  exit 0
fi

cd "$REPO_ROOT/omni/src"
"$PYTHON_BIN" -m pipeline.cli run \
  --uuid "$UUID" \
  --max-events "$MAX_EVENTS" \
  --max-workers "$MAX_WORKERS" \
  --output-dir "$OUTPUT_ROOT/data" \
  --image-dir "$OUTPUT_ROOT/image"

test -s "$OUTPUT_ROOT/data/annual_events.jsonl"
test -s "$OUTPUT_ROOT/data/image_summaries.jsonl"
test -s "$OUTPUT_ROOT/data/total_images.jsonl"
find "$OUTPUT_ROOT/image" -type f -name '*.png' -print -quit | grep -q .

printf 'Trajectory ready: %s\n' "$OUTPUT_ROOT"
