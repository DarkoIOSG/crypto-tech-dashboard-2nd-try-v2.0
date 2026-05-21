"""Audit P0 (product director + analyst): populate stocks fundamentals.

`get_market_overview` for US-stocks returned all-null for mcap / volume /
24h pct because `list_tokens()` reads stocks_universe.csv which only has
ticker/name/exchange. yfinance `Ticker.info` has all the missing fields;
this script writes them to `local_data/metadata/stocks_market.json`,
which `DataService.get_market_overview` merges in for asset_class us-stock.

One-shot + intended to be called daily by run_stocks_daily_update.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DATA_DIR, METADATA_DIR  # noqa: E402
from backend.data.yfinance_client import (  # noqa: E402
    YFinanceClient, load_stocks_universe,
)

UNIVERSE = METADATA_DIR / "stocks_universe.csv"
OUT_PATH = METADATA_DIR / "stocks_market.json"


def main():
    if not UNIVERSE.exists():
        print(f"stocks_universe.csv missing at {UNIVERSE}")
        return
    df = load_stocks_universe(UNIVERSE)
    active = df[df["active"]] if "active" in df.columns else df
    print(f"Refreshing fundamentals for {len(active)} active stocks ...")
    client = YFinanceClient()
    out = {}
    t0 = time.time()
    for i, row in enumerate(active.itertuples(index=False), 1):
        ticker = str(getattr(row, "ticker", "")).strip()
        if not ticker:
            continue
        meta = client.fetch_market_overview(ticker)
        out[ticker] = meta
        if i % 10 == 0:
            print(f"  [{i}/{len(active)}] {time.time()-t0:.0f}s elapsed")
    out["_refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2))
    tmp.replace(OUT_PATH)
    print(f"Wrote {OUT_PATH} ({time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main()
