"""R8-1D: Yahoo Finance client for US stocks (Phase-2 item 7).

Mirrors the public surface of `coingecko_client` so the Fetcher can
treat stocks as just another data source. Returns DataFrames with the
same OHLCV column shape the rest of the pipeline (indicators, scoring)
already consumes.

Key differences from the crypto path:
- Markets follow the equities calendar (no weekends, no exchange
  holidays). yfinance simply omits those days; indicator computations
  operate per-bar so weekend gaps are not a problem.
- Splits + dividends are folded into the OHLC via `auto_adjust=True` so
  the price series is continuous.
- 24h volume is reported in shares (not USD). The frontend formatter
  handles this — it shows the raw number, not a $-prefixed value.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Dict, List, Optional

import pandas as pd

from backend.config import COINGECKO_SOURCE_TAG  # unused directly, kept for symmetry


log = logging.getLogger(__name__)

STOCKS_SOURCE_TAG: str = "yfinance"


class YFinanceClient:
    """Thin wrapper around `yfinance.Ticker` for the 40-ticker US stocks
    universe defined in `local_data/metadata/stocks_universe.csv`.

    Public API mirrors CoinGeckoClient + ExchangeOHLCVClient:
        - fetch_ohlcv(ticker, days) -> Optional[pd.DataFrame]
        - fetch_market_overview(ticker) -> Dict
    """

    def __init__(self) -> None:
        # Lazy import: only constructed when needed. Keeps fastapi cold-start
        # snappy if a downstream operator never asks for stocks data.
        self._ticker_cache: Dict[str, object] = {}

    def _ticker(self, ticker: str):
        """Memoise yf.Ticker instances. Each one carries its own session."""
        if ticker not in self._ticker_cache:
            import yfinance as yf
            self._ticker_cache[ticker] = yf.Ticker(ticker)
        return self._ticker_cache[ticker]

    def fetch_ohlcv(
        self,
        ticker: str,
        days: int = 1095,
    ) -> Optional[pd.DataFrame]:
        """Return daily OHLCV for the last `days` (US trading calendar).

        Yahoo's `history(period=...)` accepts string shortcuts (1y / 2y / 5y
        / 10y / max). For arbitrary day counts we use start= and end=.
        auto_adjust=True folds splits + dividends so the OHLC continuity
        survives stock splits like 1:10 or special dividends.
        """
        end = _dt.date.today()
        start = end - _dt.timedelta(days=int(days) + 2)  # +2 for safety margin
        log.info(
            "yfinance: fetching %s ohlcv %s -> %s (%d days)",
            ticker, start, end, days,
        )
        try:
            tk = self._ticker(ticker)
            df = tk.history(
                start=str(start),
                end=str(end),
                auto_adjust=True,
                actions=False,
                prepost=False,
                back_adjust=False,
            )
        except Exception as exc:  # boundary: external API
            log.warning("yfinance fetch_ohlcv failed for %s: %s", ticker, exc)
            return None
        if df is None or df.empty:
            return None

        # Normalise to the project's OHLCV schema.
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        # Index is a DatetimeIndex with tz; convert to naive calendar date.
        if hasattr(df.index, "tz_localize"):
            try:
                df.index = df.index.tz_localize(None)
            except Exception:
                pass
        df.index = pd.to_datetime(df.index).normalize()
        df["date"] = df.index
        df["source"] = STOCKS_SOURCE_TAG
        df = df.reset_index(drop=True)
        keep = ["date", "open", "high", "low", "close", "volume", "source"]
        df = df[keep]
        # Coerce types.
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        return df.reset_index(drop=True)

    def fetch_market_overview(self, ticker: str) -> Dict:
        """Single-stock fundamentals via Ticker.info.

        Yahoo's .info varies in completeness across tickers; small caps may
        return mostly None. We do our best to extract market_cap and
        24h volume; the rest is gracefully None.
        """
        try:
            tk = self._ticker(ticker)
            info = tk.info or {}
        except Exception as exc:  # boundary
            log.warning("yfinance .info failed for %s: %s", ticker, exc)
            info = {}

        return {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName"),
            "exchange": info.get("exchange"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "total_volume_24h": info.get("regularMarketVolume"),
            "price_change_percentage_24h": info.get("regularMarketChangePercent"),
        }


def load_stocks_universe(csv_path) -> pd.DataFrame:
    """Read local_data/metadata/stocks_universe.csv as a DataFrame.

    Schema: ticker, asset_class, name, exchange, region, active.
    """
    path = str(csv_path)
    df = pd.read_csv(path)
    # Coerce active to bool.
    if "active" in df.columns:
        df["active"] = df["active"].astype(str).str.lower().isin({"true", "1", "yes"})
    return df
