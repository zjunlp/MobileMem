#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export MEMWEB_DATA_DIR="$ROOT"
export MEMWEB_PORT="${MEMWEB_PORT:-8766}"

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

exec "$PYTHON" "$ROOT/app/server.py"
