#!/usr/bin/env bash
# Double-click to launch the dashboard.
# Requirements on the host machine: Docker Desktop installed.
# Some sync/copy tools may strip the +x bit; if double-click fails once, open Terminal and:
#   chmod +x start.command stop.command
#
# Public access is handled separately by Cloudflare Named Tunnel
# (cloudflared launchd service — see NAMED_TUNNEL_SETUP.md). This script
# only brings up the Docker container; the tunnel is permanent and survives
# reboots independently.
set -uo pipefail

cd "$(dirname "$0")"

echo "════════════════════════════════════════════════════════════════"
echo "  IOSG Crypto Tech Dashboard — launcher"
echo "════════════════════════════════════════════════════════════════"
echo

# ─── 1. preflight ────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    echo "[FATAL] docker not found. Install Docker Desktop and retry."
    read -p "Press Enter to close..."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "[INFO] Docker daemon not running — trying to start Docker Desktop..."
    open -a Docker 2>/dev/null || true
    echo -n "       waiting for daemon"
    for i in $(seq 1 60); do
        if docker info >/dev/null 2>&1; then echo " ✓"; break; fi
        echo -n "."; sleep 2
    done
    if ! docker info >/dev/null 2>&1; then
        echo
        echo "[FATAL] Docker daemon never came up. Open Docker Desktop manually."
        read -p "Press Enter to close..."
        exit 1
    fi
fi

# ─── 2. build + start container ──────────────────────────────────
echo
echo "[1/2] Building image & starting container (first run ~3-5 min)..."
docker compose up -d --build

# Wait for /health to respond before declaring success.
echo -n "[2/2] Waiting for app to become healthy"
for i in $(seq 1 90); do
    if curl -sSf http://localhost:8000/health >/dev/null 2>&1; then
        echo " ✓"; break
    fi
    echo -n "."; sleep 2
done
if ! curl -sSf http://localhost:8000/health >/dev/null 2>&1; then
    echo
    echo "[FATAL] App never reported healthy on :8000. Container logs:"
    docker compose logs --tail=40
    read -p "Press Enter to close..."
    exit 1
fi

# ─── 3. report URLs ──────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════════════"
echo "  ✓ Local URL:   http://localhost:8000"
echo "  ✓ Public URL:  managed by cloudflared named tunnel (launchd)"
echo "                 see NAMED_TUNNEL_SETUP.md if not yet configured"
echo "  ✓ Access code: IOSG  (uppercase, 4 letters)"
echo "════════════════════════════════════════════════════════════════"
echo
echo "Container will keep running in the background (restart: unless-stopped)."
echo "To stop, double-click stop.command."
echo
read -p "Press Enter to close this window..."
