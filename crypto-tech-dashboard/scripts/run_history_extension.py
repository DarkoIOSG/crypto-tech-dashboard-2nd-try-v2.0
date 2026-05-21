"""R8-1B.2: one-shot CLI to extend OHLCV history to 2020-01-01.

Phase-2 item 11. Pulls every Top-N token via the 8-exchange CCXT
waterfall with HISTORY_DAYS wide enough to reach 2020-01-01 (2326 days
as of 2026-05-14). The ohlcv/ directory is snapshotted to
ohlcv_backup_YYYYMMDD/ before any write, so the whole operation is
safely reversible.

Usage:
    venv/bin/python scripts/run_history_extension.py
    venv/bin/python scripts/run_history_extension.py --target 2020-01-01
    venv/bin/python scripts/run_history_extension.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path

# Make repo root importable when run from anywhere.
_HERE = Path(__file__).resolve().parent
_PROJ = _HERE.parent
sys.path.insert(0, str(_PROJ))


def main() -> int:
    ap = argparse.ArgumentParser(description="Extend OHLCV history backward.")
    ap.add_argument(
        "--target", default="2020-01-01",
        help="Earliest date to pull. Tokens that listed after this date "
             "naturally start from their listing day. Default: 2020-01-01.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print plan + estimated runtime without modifying data.",
    )
    args = ap.parse_args()

    # Validate date.
    try:
        target_dt = _dt.date.fromisoformat(args.target)
    except ValueError as exc:
        print(f"invalid target date: {exc}", file=sys.stderr)
        return 2

    today = _dt.date.today()
    days = (today - target_dt).days
    print(f"Extension target: {args.target} ({days} days from today {today})")

    if args.dry_run:
        print("\nDRY RUN — no data modified.")
        print("Estimated runtime: ~15 min (8 exchanges × ~250 tokens × 8-call pages).")
        print("Would call: Fetcher.run_history_extension(target_start_date=…)")
        return 0

    from backend.data.fetcher import Fetcher
    from backend.data.coingecko_client import CoinGeckoClient
    from backend.data.exchange_client import ExchangeOHLCVClient
    from backend.data.local_store import LocalStore
    from backend.data.symbol_mapping import SymbolMapper
    from backend.config import DATA_DIR, METADATA_DIR

    print("\nBuilding fetcher…")
    exch = ExchangeOHLCVClient()
    cg = CoinGeckoClient()
    mapper = SymbolMapper(METADATA_DIR, exch)
    store = LocalStore(DATA_DIR)
    fetcher = Fetcher(
        exchange_client=exch,
        coingecko_client=cg,
        mapper=mapper,
        store=store,
    )

    print(f"Running history extension to {args.target} (this takes ~15 min)…\n")
    t0 = time.time()
    summary = fetcher.run_history_extension(target_start_date=args.target)
    elapsed = time.time() - t0

    print(f"\nDone in {elapsed/60:.1f} min.")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
