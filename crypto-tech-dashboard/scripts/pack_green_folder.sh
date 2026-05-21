#!/usr/bin/env bash
# R8-1A.3: pack the project as a portable "green folder" zip.
#
# What's included:
#   backend/, frontend/, scripts/, local_data/ohlcv/, local_data/market_cap/,
#   local_data/metadata/ (with .env redacted), requirements.txt, run.sh,
#   README.md, *.md docs at project root.
#
# What's excluded:
#   venv/         — platform-specific binaries (macOS arm64 doesn't run on Linux)
#   __pycache__/  — interpreter-version-locked bytecode
#   *.pyc         — same
#   .git/         — repo history is too big and not needed
#   local_data/ohlcv_backup_*/  — backups are redundant for transport
#   local_data/quarantine/      — corrupt-file dumps shouldn't ship
#   scripts/*.log  — local logs
#
# The .env that ships has COINGECKO_API_KEY replaced with a placeholder so
# the recipient cannot accidentally use the sender's Pro key. The recipient
# must edit .env before first launch (run.sh detects this and warns).
#
# Usage:
#   bash scripts/pack_green_folder.sh
#   -> writes dashboard_green_YYYYMMDD.zip in the project root

set -euo pipefail

cd "$(dirname "$0")/.."
project_root="$PWD"
out="dashboard_green_$(date +%Y%m%d).zip"

# Sanity-check: refuse to overwrite an existing zip without confirmation.
if [[ -e "$out" ]]; then
    echo "warning: $out already exists." >&2
    echo "delete it first or pick a different day; aborting." >&2
    exit 1
fi

# Redact .env before zipping, then restore.
restored_env=0
if [[ -f .env ]]; then
    cp .env .env.bak.pack
    # Replace the real key with the placeholder. Match any non-empty value.
    if grep -q '^COINGECKO_API_KEY=' .env; then
        sed -i.tmp 's|^COINGECKO_API_KEY=.*|COINGECKO_API_KEY=your-coingecko-pro-key-here|' .env
        rm -f .env.tmp
    fi
    restored_env=1
fi

# Use --quiet for clean output; --recurse-paths walks subdirs.
zip --quiet --recurse-paths "$out" . \
    --exclude "venv/*" \
              "*/__pycache__/*" "__pycache__/*" \
              "*.pyc" \
              ".git/*" ".gitignore" \
              "local_data/ohlcv_backup_*/*" \
              "local_data/quarantine/*" \
              "scripts/*.log" \
              "*.tmp" "*.bak.pack" "*.bak"

# Always restore .env, even if zip failed.
if [[ "$restored_env" -eq 1 ]]; then
    mv .env.bak.pack .env
fi

size=$(du -h "$out" | cut -f1)
files=$(unzip -l "$out" | tail -1 | awk '{print $2}')
echo
echo "✓ wrote $project_root/$out"
echo "  size: $size"
echo "  files: $files"
echo
echo "Recipient instructions:"
echo "  1. unzip $out -d crypto-tech-dashboard"
echo "  2. cd crypto-tech-dashboard"
echo "  3. edit .env (set COINGECKO_API_KEY to your own Pro key)"
echo "  4. bash scripts/setup.sh   # creates venv, installs deps"
echo "  5. ./run.sh                # starts the server on localhost:8080"
