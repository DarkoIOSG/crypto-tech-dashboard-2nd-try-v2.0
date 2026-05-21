#!/usr/bin/env bash
# One-shot setup: create venv, install requirements, copy .env, sanity-check.
# Idempotent — safe to re-run.

set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON:-python3}"

echo "==> creating venv at $(pwd)/venv"
if [[ ! -x venv/bin/python ]]; then
    "$PYTHON_BIN" -m venv venv
fi

echo "==> upgrading pip"
venv/bin/pip install --upgrade pip --quiet

echo "==> installing requirements.txt"
venv/bin/pip install -r requirements.txt --quiet

if [[ ! -f .env ]]; then
    echo "==> .env missing — copying .env.example"
    cp .env.example .env
    echo "    -> edit .env and set COINGECKO_API_KEY before first launch"
fi

mkdir -p logs

echo
echo "setup done. To run:"
echo "    ./run.sh"
echo "Or (autostart on macOS login):"
echo "    bash scripts/install_launchd.sh"
