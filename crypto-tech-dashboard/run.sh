#!/usr/bin/env bash
# Run the dashboard.
#   ./run.sh            — start uvicorn in the foreground on 127.0.0.1:8080
#   ./run.sh --public   — bind 0.0.0.0:8080 (LAN-accessible)
#   ./run.sh --port 9000

set -euo pipefail

cd "$(dirname "$0")"

HOST="127.0.0.1"
PORT="8080"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --public) HOST="0.0.0.0"; shift ;;
        --host)   HOST="$2"; shift 2 ;;
        --port)   PORT="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ ! -x venv/bin/python ]]; then
    echo "venv missing — run ./scripts/setup.sh first" >&2
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "warning: .env missing — copying .env.example to .env (you must edit COINGECKO_API_KEY)" >&2
    cp .env.example .env
fi

exec venv/bin/python -m uvicorn backend.main:app --host "$HOST" --port "$PORT"
