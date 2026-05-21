#!/usr/bin/env bash
# Double-click to stop the dashboard container.
#
# Note: Cloudflare Named Tunnel is run as a launchd service (managed via
# `cloudflared service install`, see NAMED_TUNNEL_SETUP.md) and is NOT
# touched by this script — the public URL stays available even after
# stopping the container. To stop the tunnel too, run:
#   sudo launchctl unload /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
set -uo pipefail

cd "$(dirname "$0")"

echo "════════════════════════════════════════════════════════════════"
echo "  IOSG Crypto Tech Dashboard — shutdown"
echo "════════════════════════════════════════════════════════════════"

# Clean up any legacy quick-tunnel runtime files left by older start.command
# versions. Harmless if absent.
if [ -f .runtime/cloudflared.pid ]; then
    PID=$(cat .runtime/cloudflared.pid 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[info] cleaning up legacy quick-tunnel process (pid $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm -f .runtime/cloudflared.pid
fi

# Stop the container (keeps volumes; data persists).
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "Stopping container..."
    docker compose down
else
    echo "[skip] docker daemon not running — container already down"
fi

echo
echo "  ✓ Container stopped. Data in local_data/ is preserved."
echo "  ✓ Named tunnel (if installed) is still running — public URL"
echo "    will return 502 until the container is started again."
echo "════════════════════════════════════════════════════════════════"
echo
read -p "Press Enter to close..."
