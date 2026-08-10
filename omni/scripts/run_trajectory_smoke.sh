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
USER_CONFIG_DIR="${MOBILEMEM_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/mobilemem}"
PROXY_ENV_FILE="${MOBILEMEM_PROXY_ENV_FILE:-$USER_CONFIG_DIR/proxy.env}"

if [[ -f "$PROXY_ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$PROXY_ENV_FILE"
fi

# Create the local Conda environment only when Python or pip is unavailable.
if [[ ! -x "$PYTHON_BIN" ]] \
    || ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  if [[ -n "$CUSTOM_PYTHON_BIN" ]]; then
    printf 'PYTHON_BIN must provide an executable Python with pip: %s\n' \
      "$PYTHON_BIN" >&2
    exit 1
  fi
  CONDA_BIN="${CONDA_EXE:-$(command -v conda || true)}"
  if [[ -z "$CONDA_BIN" ]]; then
    printf 'Conda is required to create the local Python environment.\n' >&2
    exit 1
  fi
  if [[ -e "$REPO_ROOT/.venv" ]]; then
    mkdir -p "$REPO_ROOT/.cache"
    BACKUP_ENV="$REPO_ROOT/.cache/incomplete-venv-$(date +%Y%m%d-%H%M%S)-$$"
    printf 'Moving incomplete environment to: %s\n' "$BACKUP_ENV"
    mv "$REPO_ROOT/.venv" "$BACKUP_ENV"
  fi
  printf 'Creating Conda environment: %s\n' "$REPO_ROOT/.venv"
  "$CONDA_BIN" create --yes --prefix "$REPO_ROOT/.venv" python=3.11 pip
fi

if ! "$PYTHON_BIN" -c '
import bs4, cv2, dotenv, html2image, jsonlines, numpy, openai, playwright
import qrcode, requests, scipy, socksio, tenacity, tqdm
from PIL import Image
' >/dev/null 2>&1; then
  printf 'Installing Python dependencies...\n'
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install \
    -r "$REPO_ROOT/omni/requirements.txt" \
    "html2image>=2,<3" "httpx[socks]>=0.27,<1"
fi

ENV_FILE="$REPO_ROOT/omni/src/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  USER_ENV_FILE="${MOBILEMEM_ENV_FILE:-$USER_CONFIG_DIR/.env}"
  if [[ -f "$USER_ENV_FILE" ]]; then
    cp "$USER_ENV_FILE" "$ENV_FILE"
  else
    cp "$REPO_ROOT/omni/src/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    printf 'Created %s. Fill in the API settings, then run this script again.\n' \
      "$ENV_FILE" >&2
    exit 1
  fi
  chmod 600 "$ENV_FILE"
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
