#!/usr/bin/env bash
# P2-4: install the launchd LaunchAgent for the dashboard. Run once on the
# Mac that will host the server. Idempotent: rerunning unloads + reloads.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$PROJECT_DIR/scripts/com.iosg.crypto-dashboard.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.iosg.crypto-dashboard.plist"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "error: missing $TEMPLATE" >&2
    exit 1
fi

if [[ ! -x "$PROJECT_DIR/venv/bin/python" ]]; then
    echo "error: $PROJECT_DIR/venv/bin/python not found — run scripts/setup.sh first" >&2
    exit 1
fi

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$(dirname "$TARGET")"

# Render the template with the absolute project path.
sed "s|PROJECT_DIR_PLACEHOLDER|$PROJECT_DIR|g" "$TEMPLATE" > "$TARGET"
echo "wrote $TARGET"

# Reload (unload first to be idempotent — `launchctl load -w` errors if already loaded).
if launchctl list | grep -q com.iosg.crypto-dashboard; then
    launchctl unload "$TARGET" 2>/dev/null || true
fi
launchctl load -w "$TARGET"

echo "loaded com.iosg.crypto-dashboard via launchctl"
echo "logs: $PROJECT_DIR/logs/uvicorn.{out,err}.log"
echo "stop:  launchctl unload -w $TARGET"
echo "check: launchctl list | grep crypto-dashboard"
