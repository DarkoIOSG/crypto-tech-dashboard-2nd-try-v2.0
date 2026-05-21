"""Phase 1.5 — Data-Layer Smoke

Verify the real data layer can fetch BTC OHLCV from a real exchange.
Steps:
  1. Build ExchangeOHLCVClient.
  2. Warm the markets cache via load_markets_all().
  3. Attempt fetch_ohlcv("BTC/USDT", "binance", days=30).
  4. Print first 3 + last 3 rows, source name, row count.

Acceptance: >= 25 rows; prices in plausible range (> 1000).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.data.exchange_client import ExchangeOHLCVClient  # noqa: E402
from backend.data.symbol_mapping import SymbolMapper  # noqa: E402
from backend.config import METADATA_DIR  # noqa: E402


def main() -> int:
    print("[smoke] building ExchangeOHLCVClient ...", flush=True)
    client = ExchangeOHLCVClient()

    print("[smoke] load_markets_all() ...", flush=True)
    markets = client.load_markets_all()
    for ex_name, m in markets.items():
        n = (len(m) if isinstance(m, dict) else 0)
        print(f"  - {ex_name}: {n} markets")

    print("[smoke] building SymbolMapper ...", flush=True)
    mapper = SymbolMapper(METADATA_DIR, client)
    # Discover just BTC so we exercise the mapper code path.
    mapper.discover([{"id": "bitcoin", "symbol": "btc"}])
    print(f"[smoke] symbol map for bitcoin: {mapper.map.get('bitcoin')}")

    # NOTE: binance + bybit are 451/403 from this region. Smoke-test against the
    # first exchange that actually answered in load_markets_all() — typically OKX.
    chosen_ex = None
    for cand in ("binance", "okx", "bybit", "gateio"):
        m = markets.get(cand)
        if isinstance(m, dict) and m:
            chosen_ex = cand
            break
    if chosen_ex is None:
        print("[smoke] FAIL: no exchange returned markets", flush=True)
        return 1

    print(f"[smoke] fetch_ohlcv BTC/USDT @ {chosen_ex} days=30 ...", flush=True)
    df = client.fetch_ohlcv("BTC/USDT", chosen_ex, days=30)
    if df is None:
        print("[smoke] FAIL: fetch_ohlcv returned None", flush=True)
        return 2
    print(f"[smoke] rows={len(df)}", flush=True)
    print(df.head(3).to_string(index=False))
    print("...")
    print(df.tail(3).to_string(index=False))

    # Also try waterfall (which uses mapper).
    print("[smoke] fetch_ohlcv_waterfall bitcoin days=30 ...", flush=True)
    df2, source = client.fetch_ohlcv_waterfall("bitcoin", days=30, mapper=mapper)
    print(f"[smoke] waterfall source={source} rows={(0 if df2 is None else len(df2))}")

    if df2 is None:
        print("[smoke] FAIL: waterfall returned None", flush=True)
        return 3

    last_close = float(df2["close"].iloc[-1])
    print(f"[smoke] last close: {last_close:.2f}")

    if len(df2) < 25:
        print(f"[smoke] FAIL: row count {len(df2)} < 25", flush=True)
        return 4
    if last_close < 1000.0:
        print(f"[smoke] FAIL: last_close={last_close} below plausible threshold 1000", flush=True)
        return 5

    print("[smoke] PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
