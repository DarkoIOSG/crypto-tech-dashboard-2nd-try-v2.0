"""Phase 2 — Indicators smoke test.

Loads BTC OHLCV via the OKX path (live fetch since no CSV cache yet) or
falls back to a synthetic 200-day price series. Then runs every family in
INDICATORS and prints output keys + last value for each. Validates:
  - RSI(14) last value in [0,100]
  - MACD hist changes sign at least once over the series.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.data.exchange_client import ExchangeOHLCVClient  # noqa: E402
from backend.indicators.registry import INDICATORS, compute_all  # noqa: E402


def _live_btc_ohlcv(days: int = 250) -> pd.DataFrame | None:
    client = ExchangeOHLCVClient()
    client.load_markets_all()
    # Prefer OKX which works in this region.
    for ex in ("okx", "gateio", "binance", "bybit"):
        df = client.fetch_ohlcv("BTC/USDT", ex, days=days)
        if df is not None and len(df) >= 30:
            print(f"[smoke_ind] using exchange={ex}, rows={len(df)}", flush=True)
            return df
    return None


def _synthetic_ohlcv(days: int = 250, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=0.001, scale=0.02, size=days)
    close = 30_000.0 * np.exp(np.cumsum(rets))
    high = close * (1.0 + np.abs(rng.normal(0, 0.01, size=days)))
    low = close * (1.0 - np.abs(rng.normal(0, 0.01, size=days)))
    open_ = close * (1.0 + rng.normal(0, 0.005, size=days))
    volume = rng.lognormal(mean=15.0, sigma=0.5, size=days)
    dates = pd.date_range("2024-01-01", periods=days, freq="D").date
    df = pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    return df


def main() -> int:
    df = _live_btc_ohlcv(days=250)
    if df is None:
        print("[smoke_ind] live fetch failed — using synthetic series", flush=True)
        df = _synthetic_ohlcv(days=250)

    print(f"[smoke_ind] rows={len(df)}  close range=[{df['close'].min():.2f}, {df['close'].max():.2f}]", flush=True)

    # ---- per-family run ----
    ok = True
    for name, fam in INDICATORS.items():
        produced = fam.compute(df)
        n_keys = len(produced)
        sample_keys = list(produced.keys())[:5]
        # Last value per key (for a single-row preview)
        last_vals = {k: produced[k].iloc[-1] if len(produced[k]) > 0 else None for k in sample_keys}
        print(f"  - {name:18s} keys={n_keys}  sample={sample_keys}  last={last_vals}")

    # ---- RSI validation ----
    rsi_dict = INDICATORS["rsi"].compute(df)
    rsi_last = float(rsi_dict["rsi_14"].iloc[-1])
    print(f"[smoke_ind] RSI(14) last = {rsi_last:.3f}")
    if not (0.0 <= rsi_last <= 100.0):
        print(f"[smoke_ind] FAIL: RSI(14)={rsi_last} not in [0,100]")
        ok = False

    # ---- MACD hist sign-change ----
    macd_dict = INDICATORS["macd"].compute(df)
    hist = macd_dict["macd_hist_12_26_9"].dropna()
    signs = np.sign(hist.values)
    changes = int(((signs[1:] != signs[:-1]) & (signs[:-1] != 0)).sum())
    print(f"[smoke_ind] MACD hist sign changes = {changes}")
    if changes < 1:
        print("[smoke_ind] FAIL: MACD hist did not change sign")
        ok = False

    # ---- compute_all sanity ----
    all_dict = compute_all(df)
    print(f"[smoke_ind] compute_all keys = {len(all_dict)}")
    if len(all_dict) < 50:
        print(f"[smoke_ind] FAIL: compute_all produced too few series ({len(all_dict)})")
        ok = False

    if not ok:
        return 1
    print("[smoke_ind] PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
