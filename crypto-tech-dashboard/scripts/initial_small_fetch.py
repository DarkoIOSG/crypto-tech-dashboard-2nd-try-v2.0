"""Tiny end-to-end fetch helper for the integration test.

Pulls top-5 by mcap from CoinGecko, then 60 days of OHLCV per token via
the exchange waterfall (OKX in this region). Writes CSVs + symbol_map +
top200_current + mcap snapshot + last_update.

Does NOT use Fetcher.run_full_initial_load (which would hit 200 tokens) —
this hand-rolls a 5-token version.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import datetime as _dt

import pandas as pd

from backend.config import COINGECKO_SOURCE_TAG, METADATA_DIR
from backend.data.coingecko_client import CoinGeckoClient
from backend.data.exchange_client import ExchangeOHLCVClient
from backend.data.local_store import LocalStore
from backend.data.symbol_mapping import SymbolMapper


N_TOKENS = 5
DAYS = 60


def _coingecko_close_to_ohlcv(df_close: pd.DataFrame) -> pd.DataFrame:
    if df_close is None or df_close.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    out = df_close.copy()
    out["open"] = out["close"]
    out["high"] = out["close"]
    out["low"] = out["close"]
    out["volume"] = 0.0
    return out[["date", "open", "high", "low", "close", "volume"]]


def main() -> int:
    # CoinGecko's pro API SSL-handshakes are flaky from this Mac (same root-
    # cause as the pypi.org issue noted in the build env). For the integration
    # smoke we fall back to a small hard-coded universe so we can still exercise
    # the OHLCV pipeline + API end-to-end. This shortcut is integration-test-
    # only; the production daily-update path still uses CoinGeckoClient.
    print(f"[initial] fetching top-{N_TOKENS} (CoinGecko, with fallback)...", flush=True)
    cg = CoinGeckoClient()
    top_df = cg.fetch_top_n_markets(n=N_TOKENS)
    if top_df.empty:
        print("[initial] CoinGecko unreachable -> using built-in 5-token universe", flush=True)
        top_df = pd.DataFrame(
            [
                {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": None, "market_cap": 1_700e9},
                {"id": "ethereum", "symbol": "eth", "name": "Ethereum", "current_price": None, "market_cap": 400e9},
                {"id": "solana", "symbol": "sol", "name": "Solana", "current_price": None, "market_cap": 80e9},
                {"id": "ripple", "symbol": "xrp", "name": "XRP", "current_price": None, "market_cap": 60e9},
                {"id": "cardano", "symbol": "ada", "name": "Cardano", "current_price": None, "market_cap": 20e9},
            ]
        )
    print(f"[initial]   universe={len(top_df)} tokens")
    print(top_df[["id", "symbol", "market_cap"]].to_string(index=False))

    exch = ExchangeOHLCVClient()
    exch.load_markets_all()
    mapper = SymbolMapper(METADATA_DIR, exch)
    mapper.discover(top_df[["id", "symbol"]].to_dict(orient="records"))

    store = LocalStore(ROOT / "local_data")

    success = 0
    fallback = 0
    failed = 0
    for row in top_df.itertuples(index=False):
        cg_id = getattr(row, "id")
        df, source = exch.fetch_ohlcv_waterfall(cg_id=cg_id, days=DAYS, mapper=mapper)
        if df is not None and not df.empty:
            store.write_ohlcv(cg_id, df, source)
            success += 1
            print(f"[initial]   {cg_id:20s} -> {source} ({len(df)} rows)")
            continue

        # Skip CoinGecko fallback in the integration smoke — same TLS issue.
        failed += 1
        print(f"[initial]   {cg_id:20s} -> FAILED")

    # Universe snapshot + mcap snapshot
    store.write_top200_current(top_df)
    today = _dt.date.today()
    mcap_snap = pd.DataFrame({"cg_id": top_df["id"], "mcap": top_df["market_cap"]})
    store.write_mcap_snapshot(today, mcap_snap)
    store.write_last_update(
        {
            "last_ohlcv_update": _dt.datetime.now().isoformat(timespec="seconds"),
            "last_mcap_update": _dt.datetime.now().isoformat(timespec="seconds"),
            "status": "idle",
            "mode": "small_initial_load",
            "last_run_summary": {
                "success": success,
                "fallback": fallback,
                "failed": failed,
            },
        }
    )

    print(f"[initial] done success={success} fallback={fallback} failed={failed}")
    if success + fallback == 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
