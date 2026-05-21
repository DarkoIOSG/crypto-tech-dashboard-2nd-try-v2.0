"""R8-1B (stocks) · Plan item 11 acceptance:
"pre-2020 stocks must reach 2020-01-01; post-2020 IPOs start from listing day".

The crypto history extension (run_history_extension.py) ran the CCXT
waterfall to 2020. The stocks side stayed at the default 1095-day
fetch — MSTR (1998 IPO), COIN (2021 IPO), MARA (2010 IPO) etc. all
truncated at 2023-05-15. yfinance can deliver the full history; this
script does the equivalent one-shot.

Strategy:
  1. Load active stocks_universe.csv tickers.
  2. For each, fetch yfinance OHLCV with days=2326 (≥ 2020-01-02 today).
  3. yfinance correctly returns less when the listing is post-2020,
     so post-2020 IPOs naturally start at their listing day.
  4. Atomic-write each CSV via LocalStore.write_ohlcv.
  5. Update data_coverage.json for each ticker with the listing date
     range observed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import datetime as _dt
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DATA_DIR, METADATA_DIR
from backend.data.local_store import LocalStore
from backend.data.yfinance_client import YFinanceClient

STOCKS_UNIVERSE = METADATA_DIR / "stocks_universe.csv"
DATA_COVERAGE = METADATA_DIR / "data_coverage.json"
TARGET = _dt.date.fromisoformat("2020-01-01")
TODAY = _dt.date.today()
DAYS = (TODAY - TARGET).days + 2   # +2 for safety margin


def _load_coverage() -> dict:
    if DATA_COVERAGE.exists():
        return json.loads(DATA_COVERAGE.read_text())
    return {}


def _save_coverage(d: dict) -> None:
    tmp = DATA_COVERAGE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(DATA_COVERAGE)


def main():
    print(f"Target: history reaching {TARGET} (days={DAYS}, today={TODAY})")
    if not STOCKS_UNIVERSE.exists():
        print(f"stocks_universe.csv missing at {STOCKS_UNIVERSE}")
        return
    universe = pd.read_csv(STOCKS_UNIVERSE)
    active = universe[universe["active"].astype(str).str.lower() == "true"]
    print(f"Active stocks to extend: {len(active)} of {len(universe)} declared")

    store = LocalStore(DATA_DIR)
    yf = YFinanceClient()
    coverage = _load_coverage()

    success = 0
    short = []   # listing post-2020, expected
    failed = []
    t0 = time.time()
    for i, row in active.iterrows():
        ticker = str(row["ticker"])
        df = yf.fetch_ohlcv(ticker, days=DAYS)
        if df is None or df.empty:
            failed.append(ticker)
            print(f"  [{i+1}/{len(active)}] {ticker}: FAIL (no data)")
            continue
        store.write_ohlcv(ticker, df, "yfinance")
        first = pd.to_datetime(df["date"]).min().date()
        last = pd.to_datetime(df["date"]).max().date()
        if first <= TARGET:
            success += 1
            tag = "to-2020"
        else:
            short.append((ticker, str(first)))
            tag = f"post-2020-IPO ({first})"
        print(f"  [{i+1}/{len(active)}] {ticker}: {len(df)} rows  {first}→{last}  {tag}")
        coverage[ticker] = {
            "earliest_date": str(first),
            "latest_date": str(last),
            "listing_date": str(first),
            "real_ohlc_from": str(first),
            "close_only_windows": [],
            "tier_breakdown": [{
                "from": str(first), "to": str(last),
                "tier": 1, "source": "yfinance", "rows": int(len(df)),
            }],
        }

    _save_coverage(coverage)
    print(f"\nDone in {time.time()-t0:.0f}s")
    print(f"  to-2020: {success}")
    print(f"  post-2020 IPO (expected listing-day start): {len(short)}")
    print(f"  failed: {len(failed)}  {failed}")


if __name__ == "__main__":
    main()
