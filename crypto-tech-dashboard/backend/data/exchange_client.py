"""
backend/data/exchange_client.py
================================

Thin CCXT wrapper that pulls daily OHLCV from Binance -> OKX -> Bybit -> Gate.io
with a waterfall fallback. CoinGecko close-price fallback lives in
`coingecko_client.py` and is invoked by `fetcher.py` only when this module
returns `(None, "none")`.

try/except is intentionally used here (option C — external-API wrappers only).
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple, TYPE_CHECKING

import ccxt
import pandas as pd

from backend.config import (
    EXCHANGE_OHLCV_LIMIT,
    EXCHANGE_PRIORITY,
    MIN_OHLCV_ROWS,
)

if TYPE_CHECKING:
    from backend.data.symbol_mapping import SymbolMapper


logger = logging.getLogger("backend.data.exchange_client")


# Per-exchange daily-bar per-call cap. CCXT exposes these via market metadata
# but values vary by API tier; hard-code conservatively so pagination is
# correct without runtime guessing.
PER_CALL_LIMIT: dict[str, int] = {
    "binance": 1000,
    "okx": 300,
    "bybit": 1000,
    "gateio": 1000,
    # R8-1B.1: extra exchanges to maximise Tier-1 coverage (Phase-2 item 11).
    # Per-call caps verified from each exchange's public REST docs.
    "coinbase": 300,    # Coinbase Advanced Trade /products/{}/candles
    "kraken": 720,      # Kraken /OHLC accepts since= but pages of ~720
    "kucoin": 1500,     # KuCoin /market/candles
    "bitstamp": 1000,   # Bitstamp /v2/ohlc/{currency_pair}
}
_DEFAULT_PER_CALL_LIMIT: int = 300
_DAY_MS: int = 86_400_000


class ExchangeOHLCVClient:
    """
    Multi-exchange daily OHLCV client.

    Public API:
        - load_markets_all()
        - fetch_ohlcv(symbol_pair, exchange, days) -> DataFrame | None
        - fetch_ohlcv_waterfall(cg_id, days, mapper) -> (DataFrame | None, source_name)
        - markets_for(exchange) -> dict | None  (cached load_markets() result)
    """

    def __init__(self) -> None:
        # `enableRateLimit=True` lets CCXT pace requests according to each
        # exchange's published throughput budget.
        # R8-1B.1: 8-exchange Tier-1 waterfall. Order MATCHES
        # backend.config.EXCHANGE_PRIORITY so the dict iteration in
        # load_markets_all() / fetch_ohlcv_waterfall() respects priority.
        self.exchanges: dict[str, "ccxt.Exchange"] = {
            "binance":  ccxt.binance({"enableRateLimit": True, "timeout": 30000}),
            "okx":      ccxt.okx({"enableRateLimit": True, "timeout": 30000}),
            "bybit":    ccxt.bybit({"enableRateLimit": True, "timeout": 30000}),
            "gateio":   ccxt.gateio({"enableRateLimit": True, "timeout": 30000}),
            "coinbase": ccxt.coinbase({"enableRateLimit": True, "timeout": 30000}),
            "kraken":   ccxt.kraken({"enableRateLimit": True, "timeout": 30000}),
            "kucoin":   ccxt.kucoin({"enableRateLimit": True, "timeout": 30000}),
            "bitstamp": ccxt.bitstamp({"enableRateLimit": True, "timeout": 30000}),
        }
        # Cache of `.load_markets()` output per exchange.
        self._markets_cache: dict[str, Optional[dict]] = {
            name: None for name in self.exchanges
        }
        self._markets_loaded: bool = False

    # ------------------------------------------------------------------ #
    # Markets cache
    # ------------------------------------------------------------------ #
    def load_markets_all(self) -> dict[str, Optional[dict]]:
        """Call `.load_markets()` once per exchange and cache results."""
        for name in EXCHANGE_PRIORITY:
            ex = self.exchanges.get(name)
            if ex is None:
                continue
            if self._markets_cache.get(name) is not None:
                continue
            try:
                logger.info("loading markets for %s ...", name)
                markets = ex.load_markets()
                self._markets_cache[name] = markets
                logger.info("  %s: %d markets loaded", name, len(markets))
            except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
                logger.warning("load_markets failed for %s: %s", name, exc)
                self._markets_cache[name] = None
            except Exception as exc:  # noqa: BLE001 - external-API fallback
                logger.warning(
                    "load_markets unexpected error for %s: %s", name, exc
                )
                self._markets_cache[name] = None
        self._markets_loaded = True
        return self._markets_cache

    def markets_for(self, exchange: str) -> Optional[dict]:
        """Return cached markets dict for the named exchange (or None)."""
        if not self._markets_loaded:
            self.load_markets_all()
        return self._markets_cache.get(exchange)

    # ------------------------------------------------------------------ #
    # Single-exchange fetch
    # ------------------------------------------------------------------ #
    def fetch_ohlcv(
        self,
        symbol_pair: str,
        exchange: str,
        days: int = EXCHANGE_OHLCV_LIMIT,
    ) -> Optional[pd.DataFrame]:
        """
        Try fetching daily OHLCV from a single exchange.

        Paginates with `since=` to honour the per-exchange per-call cap
        (PER_CALL_LIMIT). OKX in particular caps at ~300 bars per call, so a
        request for 1095 days requires ~4 page calls walking forward in time.

        Args:
            symbol_pair: CCXT-style unified symbol, e.g. "BTC/USDT".
            exchange:    Lower-case exchange name in EXCHANGE_PRIORITY.
            days:        Bars to request (history depth, in days).

        Returns:
            DataFrame with columns [date, open, high, low, close, volume]
            sorted ascending by date, deduped by date — or None on failure
            / insufficient rows.
        """
        ex = self.exchanges.get(exchange)
        if ex is None:
            logger.debug("unknown exchange: %s", exchange)
            return None
        if symbol_pair is None or "/" not in symbol_pair:
            logger.debug("invalid symbol_pair: %r", symbol_pair)
            return None

        target_days = max(1, min(int(days), EXCHANGE_OHLCV_LIMIT * 4))
        per_call_limit = PER_CALL_LIMIT.get(exchange, _DEFAULT_PER_CALL_LIMIT)

        now_ms = ex.milliseconds()
        # Pad by 1 day on the lower bound so we don't miss the very first bar
        # due to floor-rounding inside exchange APIs.
        since_ms = now_ms - (target_days + 1) * _DAY_MS

        all_rows: list[list] = []
        cursor_ms = since_ms
        # Cap loop iterations defensively: target_days / per_call_limit + a
        # small buffer. Each iteration must advance cursor by at least 1 day.
        max_iters = (target_days // max(1, per_call_limit)) + 5

        for _iteration in range(max_iters):
            if cursor_ms >= now_ms:
                break

            page: Optional[list] = None
            try:
                page = ex.fetch_ohlcv(
                    symbol_pair,
                    timeframe="1d",
                    since=int(cursor_ms),
                    limit=per_call_limit,
                )
            except ccxt.NetworkError as exc:
                logger.info(
                    "fetch_ohlcv NetworkError on %s for %s (since=%d): %s",
                    exchange,
                    symbol_pair,
                    cursor_ms,
                    exc,
                )
                break
            except ccxt.ExchangeError as exc:
                logger.info(
                    "fetch_ohlcv ExchangeError on %s for %s (since=%d): %s",
                    exchange,
                    symbol_pair,
                    cursor_ms,
                    exc,
                )
                break
            except Exception as exc:  # noqa: BLE001 - external-API fallback
                logger.warning(
                    "fetch_ohlcv unexpected error on %s for %s (since=%d): %s",
                    exchange,
                    symbol_pair,
                    cursor_ms,
                    exc,
                )
                break

            if not page:
                # Exchange returned an empty page — we've passed the listing
                # window or hit the right edge of available history.
                break

            all_rows.extend(page)

            last_ts = page[-1][0]
            if not isinstance(last_ts, (int, float)):
                break
            # Advance the cursor past the last returned candle. If the page
            # didn't advance (rare misbehaviour), step forward one bar to
            # guarantee progress.
            next_cursor = int(last_ts) + _DAY_MS
            if next_cursor <= cursor_ms:
                next_cursor = cursor_ms + _DAY_MS
            cursor_ms = next_cursor

            # NOTE on the "short-page" heuristic (P0-B fix):
            # We do NOT break when len(page) < per_call_limit. Multiple
            # exchanges (gateio, okx) routinely return pages well below the
            # nominal cap even when more recent bars are available — the
            # previous heuristic was the root cause of ~half the universe
            # being stuck months behind (see commit message). The outer
            # `cursor_ms >= now_ms` guard plus the empty-page break above are
            # the correct termination conditions.

        # Row-count gate: full-history loads must clear MIN_OHLCV_ROWS so
        # downstream scoring has at least a window of bars to work with.
        # For short lookbacks (e.g. the 5-day daily update), getting back N
        # rows when we asked for N rows is correct — applying MIN_OHLCV_ROWS
        # there caused P0-H (run_daily_update returned None for every token
        # and the 100% CG-fallback path took over). Required floor =
        # min(MIN_OHLCV_ROWS, target_days).
        required_rows = min(MIN_OHLCV_ROWS, target_days)
        if not all_rows or len(all_rows) < required_rows:
            logger.debug(
                "fetch_ohlcv from %s for %s returned %d rows (< %d) — skipping",
                exchange,
                symbol_pair,
                len(all_rows),
                required_rows,
            )
            return None

        df = pd.DataFrame(
            all_rows,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        # Normalize timestamp -> UTC calendar date (matches exchange UTC 00:00 candles).
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.date
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df = df.drop_duplicates(subset="date", keep="last")
        df = df.sort_values("date").reset_index(drop=True)
        # Clip to the most recent `target_days` bars (waterfall callers ask for
        # 1095 days but listings older than that should also be trimmed).
        if len(df) > target_days:
            df = df.tail(target_days).reset_index(drop=True)
        return df

    # ------------------------------------------------------------------ #
    # Waterfall
    # ------------------------------------------------------------------ #
    def fetch_ohlcv_waterfall(
        self,
        cg_id: str,
        days: int,
        mapper: "SymbolMapper",
    ) -> Tuple[Optional[pd.DataFrame], str]:
        """
        Walk EXCHANGE_PRIORITY for `cg_id`, returning the first hit.

        Args:
            cg_id:  CoinGecko id (e.g. "bitcoin").
            days:   Days requested.
            mapper: A2's SymbolMapper providing `get_symbol(cg_id, exchange) -> str | None`.

        Returns:
            (DataFrame, source_name) on success, else (None, "none").
        """
        if mapper is None:
            logger.warning("fetch_ohlcv_waterfall called with mapper=None")
            return None, "none"

        # Same min-rows logic as fetch_ohlcv: full-history pulls must clear
        # MIN_OHLCV_ROWS, but a 5-day daily update is happy with N rows when
        # the caller asked for N. Previously the hard floor here meant
        # every daily refresh fell back to CG (P0-H).
        required_rows = min(MIN_OHLCV_ROWS, max(1, int(days)))

        for exchange in EXCHANGE_PRIORITY:
            symbol_pair = mapper.get_symbol(cg_id, exchange)
            if not symbol_pair:
                continue

            df = self.fetch_ohlcv(symbol_pair, exchange, days=days)
            if df is not None and len(df) >= required_rows:
                logger.info(
                    "ohlcv waterfall: %s -> %s (%s) %d rows",
                    cg_id,
                    exchange,
                    symbol_pair,
                    len(df),
                )
                return df, exchange

            # Brief pause between exchange attempts to avoid hammering when
            # cascading through failures.
            time.sleep(0.2)

        logger.info("ohlcv waterfall: %s -> none (all exchanges failed)", cg_id)
        return None, "none"
