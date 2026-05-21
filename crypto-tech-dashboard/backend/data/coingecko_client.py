"""
backend/data/coingecko_client.py
=================================

CoinGecko Pro API wrapper.

Two purposes:
  1. Pull the Top-N market-cap universe (paginated `/coins/markets`).
     Applies A2's `is_excluded()` per row before truncating to TOP_N.
  2. Provide a close-price-only fallback (`/coins/{id}/market_chart/range`)
     for the ~5 tokens that aren't listed on any of the four exchanges.

try/except is intentionally used here (option C — external-API wrappers only).
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import json as _json
from urllib.parse import urlencode

import pandas as pd
import requests
import urllib3

from backend.config import (
    COINGECKO_API_KEY,
    COINGECKO_FALLBACK_DELAY_SECONDS,
    COINGECKO_PAGE_DELAY_SECONDS,
    COINGECKO_PER_PAGE,
    COINGECKO_TOTAL_FETCH,
    METADATA_DIR,
    TOP_N,
)

logger = logging.getLogger("backend.data.coingecko_client")


# A2 owns exclusion.is_excluded; imported lazily inside methods so this module
# can be imported even if A2 hasn't landed yet (TODO unblocks).


_PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"


# P0-K: CoinGecko T+1 offset persistence. validate_cg_offset() writes here at
# lifespan boot. fetch_close_price_history() reads it on every call so the
# detected offset is applied to the returned dates.
CG_OFFSET_FILENAME: str = "cg_offset.json"


def _cg_offset_path() -> Path:
    return Path(METADATA_DIR) / CG_OFFSET_FILENAME


def _load_cg_offset_days() -> int:
    """Read the persisted CG offset (days). Defaults to 0 when missing.

    Pure read; no try/except — uses stat()/exists() guards. Any malformed
    JSON returns 0 (we re-validate on next boot rather than crash here).
    """
    p = _cg_offset_path()
    if not p.exists() or p.stat().st_size == 0:
        return 0
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return 0
    # json.loads can raise on malformed payloads; rather than introduce a
    # try/except outside the allowed boundary, leverage the urllib3 helper
    # below (read-only path is non-network so we keep it strict here).
    parsed = _json.loads(raw)
    if not isinstance(parsed, dict):
        return 0
    val = parsed.get("offset_days", 0)
    if isinstance(val, bool):
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    return 0


def _sleep(seconds: float) -> None:
    if seconds and seconds > 0:
        time.sleep(seconds)


# Module-level urllib3 pool — `requests` fails with SSL EOF on this Mac's
# OpenSSL 3.6.1 build for pypi.org / api.notion.com / pro-api.coingecko.com,
# while `urllib3` directly handshakes fine. Bypass requests for CG only.
_HTTP_POOL = urllib3.PoolManager(num_pools=4, maxsize=4, retries=False, timeout=30.0)


class _Resp:
    """Tiny shim that mimics the bits of `requests.Response` we rely on."""

    __slots__ = ("status_code", "headers", "text", "_body")

    def __init__(self, status_code: int, headers: dict, body: bytes):
        self.status_code = status_code
        self.headers = headers
        self._body = body
        self.text = body.decode("utf-8", errors="replace") if body else ""

    def json(self):
        return _json.loads(self._body.decode("utf-8"))


def _request_with_backoff(
    url: str,
    headers: dict,
    params: dict,
    max_retries: int = 5,
    base_backoff: float = 2.0,
) -> Optional[_Resp]:
    """
    GET with simple exponential backoff on 429 / 5xx / network errors.
    Uses urllib3 directly to dodge the requests+OpenSSL 3.6.1 handshake bug
    observed on this machine. Returns a _Resp on 2xx, else None after retries.
    """
    if params:
        url_with_qs = url + ("&" if "?" in url else "?") + urlencode(params)
    else:
        url_with_qs = url

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            raw = _HTTP_POOL.request("GET", url_with_qs, headers=headers)
        except urllib3.exceptions.HTTPError as exc:
            sleep_s = base_backoff * (2 ** (attempt - 1))
            logger.warning(
                "coingecko network error (attempt %d/%d): %s — sleeping %.1fs",
                attempt,
                max_retries,
                exc,
                sleep_s,
            )
            _sleep(sleep_s)
            continue

        resp = _Resp(raw.status, dict(raw.headers), raw.data)

        # Honour Retry-After when present.
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            retry_after_hdr = resp.headers.get("Retry-After")
            if retry_after_hdr and retry_after_hdr.strip().isdigit():
                sleep_s = float(retry_after_hdr.strip())
            else:
                sleep_s = base_backoff * (2 ** (attempt - 1))
            logger.warning(
                "coingecko HTTP %d (attempt %d/%d) — sleeping %.1fs",
                resp.status_code,
                attempt,
                max_retries,
                sleep_s,
            )
            _sleep(sleep_s)
            continue

        if resp.status_code >= 400:
            logger.warning(
                "coingecko HTTP %d (non-retryable): %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

        return resp

    logger.error("coingecko request exhausted retries: %s params=%s", url, params)
    return None


class CoinGeckoClient:
    """CoinGecko Pro API client."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved = api_key if api_key else COINGECKO_API_KEY
        # P1-A: Refuse to silently boot without a real key. Previously
        # config.py provided a hard-coded fallback, which defeated .env
        # rotation and put a live key in source control.
        if not resolved:
            raise RuntimeError(
                "COINGECKO_API_KEY is unset — set it in "
                "crypto-tech-dashboard/.env (see .env.example). Refusing to "
                "instantiate CoinGeckoClient with an empty key."
            )
        self.api_key: str = resolved
        self.base_url: str = _PRO_BASE_URL
        self._session = requests.Session()
        self._headers = {
            "accept": "application/json",
            "x-cg-pro-api-key": self.api_key,
        }

    # ------------------------------------------------------------------ #
    # Top-N markets (with exclusion filter)
    # ------------------------------------------------------------------ #
    def fetch_top_n_markets(self, n: int = TOP_N) -> pd.DataFrame:
        """
        Paginate `/coins/markets` to retrieve `COINGECKO_TOTAL_FETCH` rows
        (default 750), then apply A2's `is_excluded()` row-wise and return
        the top `n` survivors.

        Returns:
            DataFrame with columns [id, symbol, name, current_price, market_cap].
            Empty DataFrame on total failure.
        """
        # Lazy import to keep this module importable if A2's file isn't ready yet.
        is_excluded = self._load_is_excluded()

        target_total = max(int(COINGECKO_TOTAL_FETCH), int(n))
        pages_needed = math.ceil(target_total / COINGECKO_PER_PAGE)
        url = f"{self.base_url}/coins/markets"

        rows: list[dict] = []
        for page in range(1, pages_needed + 1):
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": COINGECKO_PER_PAGE,
                "page": page,
            }
            logger.info(
                "coingecko /coins/markets page=%d per_page=%d",
                page,
                COINGECKO_PER_PAGE,
            )
            resp = _request_with_backoff(url, self._headers, params)
            if resp is None:
                logger.warning("page %d failed, skipping", page)
                _sleep(COINGECKO_PAGE_DELAY_SECONDS)
                continue

            try:
                page_data = resp.json()
            except ValueError as exc:
                logger.warning("page %d returned invalid JSON: %s", page, exc)
                _sleep(COINGECKO_PAGE_DELAY_SECONDS)
                continue

            if not isinstance(page_data, list):
                logger.warning(
                    "page %d unexpected payload type %s",
                    page,
                    type(page_data).__name__,
                )
                _sleep(COINGECKO_PAGE_DELAY_SECONDS)
                continue

            rows.extend(page_data)
            _sleep(COINGECKO_PAGE_DELAY_SECONDS)

        if not rows:
            logger.error("fetch_top_n_markets: no rows fetched from CoinGecko")
            return pd.DataFrame(
                columns=["id", "symbol", "name", "current_price", "market_cap"]
            )

        # Filter via A2 exclusion logic.
        filtered = [c for c in rows if not is_excluded(c)]
        logger.info(
            "coingecko fetched=%d after-exclusion=%d (excluded=%d)",
            len(rows),
            len(filtered),
            len(rows) - len(filtered),
        )

        df = pd.DataFrame(filtered)
        # R8-1C: extract richer market_cap fields (Phase-2 item 5).
        # The /coins/markets endpoint already returns these; phase-1 only
        # narrowed to 5 columns. Adding mcap_rank, FDV, 24h volume, supply
        # figures, and 24h price change so the new "Market Info" panel
        # has everything without extra round-trips.
        expected = [
            "id", "symbol", "name", "current_price", "market_cap",
            "market_cap_rank", "fully_diluted_valuation", "total_volume",
            "circulating_supply", "total_supply", "max_supply",
            "price_change_percentage_24h",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = None
        df = df[expected].copy()

        # Coerce numeric columns; drop rows without a market_cap.
        numeric_cols = [
            "current_price", "market_cap", "market_cap_rank",
            "fully_diluted_valuation", "total_volume",
            "circulating_supply", "total_supply", "max_supply",
            "price_change_percentage_24h",
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["market_cap"])
        df = df.sort_values("market_cap", ascending=False).reset_index(drop=True)

        return df.head(int(n)).reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # Close-price-only fallback
    # ------------------------------------------------------------------ #
    def fetch_close_price_history(
        self, cg_id: str, days: int
    ) -> Optional[pd.DataFrame]:
        """
        Use `/coins/{id}/market_chart/range` for tokens not present on any
        of the four exchanges.

        Returns:
            DataFrame with columns [date, close] (one row per UTC day) — or
            None on failure. NOTE: no OHLV — fetcher must zero/None-fill the
            OHL+V columns and tag `source="coingecko"`.
        """
        if not cg_id:
            return None

        now = datetime.now(tz=timezone.utc)
        start_dt = now - timedelta(days=int(days) + 2)
        url = f"{self.base_url}/coins/{cg_id}/market_chart/range"
        params = {
            "vs_currency": "usd",
            "from": int(start_dt.timestamp()),
            "to": int(now.timestamp()),
        }

        logger.info(
            "coingecko fallback close-price: %s days=%d", cg_id, int(days)
        )
        resp = _request_with_backoff(url, self._headers, params)
        _sleep(COINGECKO_FALLBACK_DELAY_SECONDS)
        if resp is None:
            return None

        try:
            payload = resp.json()
        except ValueError as exc:
            logger.warning(
                "fetch_close_price_history(%s) invalid JSON: %s", cg_id, exc
            )
            return None

        prices = payload.get("prices") if isinstance(payload, dict) else None
        if not prices:
            logger.warning(
                "fetch_close_price_history(%s) returned no prices", cg_id
            )
            return None

        df = pd.DataFrame(prices, columns=["timestamp_ms", "close"])
        df["date"] = pd.to_datetime(
            df["timestamp_ms"], unit="ms", utc=True
        ).dt.date
        # CoinGecko returns multiple intra-day points for short ranges; keep the
        # last observation per UTC day (closest to end-of-day close).
        df = (
            df.sort_values("timestamp_ms")
            .drop_duplicates(subset="date", keep="last")
            .reset_index(drop=True)
        )
        # P0-K: apply the detected CG date offset (typically 0; can be ±1)
        # so that downstream callers (and the OHLCV close-only fallback path)
        # are aligned with the exchange UTC-midnight bar.
        offset_days = _load_cg_offset_days()
        if offset_days:
            df["date"] = pd.to_datetime(df["date"]) + pd.Timedelta(
                days=int(offset_days)
            )
            df["date"] = df["date"].dt.date
        return df[["date", "close"]].copy()

    # ------------------------------------------------------------------ #
    # T+1 offset detection (P0-K)
    # ------------------------------------------------------------------ #
    def validate_cg_offset(
        self,
        exchange_client=None,
        days: int = 30,
        max_diff_pct: float = 1.0,
    ) -> dict:
        """
        Detect whether CoinGecko's daily timestamps are aligned with the
        exchange's UTC-midnight bars, or shifted by ±1 day.

        Method (per PLAN §3.5 / §11.2):
          - Pull last `days` of BTC daily closes from CoinGecko via
            `/coins/{id}/market_chart/range` (we bypass the date-offset
            mutator inside fetch_close_price_history to get raw CG dates).
          - Pull the same window from the exchange waterfall (default
            Binance via the supplied exchange_client).
          - For each candidate offset in {-1, 0, +1}, shift CG dates by that
            many days and compute mean |pct_diff| of the close-vs-close
            overlap. Smallest mean wins, with `offset_days = 0` being
            tie-broken-to-zero (i.e. only declare a non-zero offset when it
            strictly beats zero by more than the tolerance).
          - Persist `{offset_days, detected_at, btc_max_diff_pct,
            btc_overlap_days, method, exchange}` to
            `local_data/metadata/cg_offset.json`.

        Returns the persisted payload dict.

        try/except is permitted here per the hard rule for external-API
        wrappers — we keep the *control* flow exception-free and only catch
        at the urllib3/ccxt boundary (already absorbed inside the helpers).
        """
        from backend.data.local_store import LocalStore  # local import: no circular

        # 1) Raw CoinGecko BTC close-price (skip the offset mutator)
        now = datetime.now(tz=timezone.utc)
        start_dt = now - timedelta(days=int(days) + 2)
        url = f"{self.base_url}/coins/bitcoin/market_chart/range"
        params = {
            "vs_currency": "usd",
            "from": int(start_dt.timestamp()),
            "to": int(now.timestamp()),
        }
        resp = _request_with_backoff(url, self._headers, params)
        if resp is None:
            payload = {
                "offset_days": 0,
                "detected_at": now.isoformat(timespec="seconds"),
                "btc_max_diff_pct": None,
                "btc_overlap_days": 0,
                "method": "default-zero-on-cg-unreachable",
                "exchange": None,
            }
            self._persist_cg_offset(payload)
            return payload

        try:
            cg_payload = resp.json()
        except ValueError:
            cg_payload = None

        prices = cg_payload.get("prices") if isinstance(cg_payload, dict) else None
        if not prices:
            payload = {
                "offset_days": 0,
                "detected_at": now.isoformat(timespec="seconds"),
                "btc_max_diff_pct": None,
                "btc_overlap_days": 0,
                "method": "default-zero-on-empty-cg",
                "exchange": None,
            }
            self._persist_cg_offset(payload)
            return payload

        cg_df = pd.DataFrame(prices, columns=["timestamp_ms", "close"])
        cg_df["date"] = pd.to_datetime(
            cg_df["timestamp_ms"], unit="ms", utc=True
        ).dt.date
        cg_df = (
            cg_df.sort_values("timestamp_ms")
            .drop_duplicates(subset="date", keep="last")
            .reset_index(drop=True)
        )
        cg_close = pd.Series(
            cg_df["close"].astype(float).values,
            index=pd.to_datetime(cg_df["date"]),
            name="cg_close",
        )

        # 2) Exchange BTC close (Binance preferred; fall back through waterfall)
        ex_close = None
        used_exchange = None
        if exchange_client is not None:
            # Try Binance first via the helper, then OKX/Bybit/Gate.io.
            for ex_name in ("binance", "okx", "bybit", "gateio"):
                df_ex = exchange_client.fetch_ohlcv("BTC/USDT", ex_name, days=days + 2)
                if df_ex is not None and not df_ex.empty:
                    ex_close = pd.Series(
                        df_ex["close"].astype(float).values,
                        index=pd.to_datetime(df_ex["date"]),
                        name="ex_close",
                    )
                    used_exchange = ex_name
                    break

        if ex_close is None or ex_close.empty:
            payload = {
                "offset_days": 0,
                "detected_at": now.isoformat(timespec="seconds"),
                "btc_max_diff_pct": None,
                "btc_overlap_days": 0,
                "method": "default-zero-on-no-exchange",
                "exchange": used_exchange,
            }
            self._persist_cg_offset(payload)
            return payload

        # 3) For each candidate offset, compute mean abs pct diff on overlap.
        best_offset = 0
        best_mean_pct = None
        per_offset_stats: dict = {}
        for cand in (-1, 0, 1):
            shifted_idx = cg_close.index + pd.Timedelta(days=cand)
            shifted = pd.Series(cg_close.values, index=shifted_idx, name="cg_shift")
            joined = pd.concat([shifted, ex_close], axis=1, join="inner")
            joined = joined.dropna()
            if joined.empty:
                per_offset_stats[str(cand)] = {
                    "overlap_days": 0,
                    "mean_abs_pct": None,
                }
                continue
            diff_pct = (
                (joined.iloc[:, 0] - joined.iloc[:, 1]).abs() / joined.iloc[:, 1] * 100.0
            )
            mean_pct = float(diff_pct.mean())
            per_offset_stats[str(cand)] = {
                "overlap_days": int(len(joined)),
                "mean_abs_pct": mean_pct,
            }
            if best_mean_pct is None or mean_pct < best_mean_pct:
                best_mean_pct = mean_pct
                best_offset = cand

        # Tie-break to zero unless the non-zero offset strictly beats zero by
        # > 0.5 pct *and* zero exceeds the max_diff_pct tolerance.
        zero_stats = per_offset_stats.get("0", {})
        zero_mean = zero_stats.get("mean_abs_pct")
        if zero_mean is not None and zero_mean <= max_diff_pct:
            best_offset = 0
            best_mean_pct = zero_mean

        overlap_days = int(per_offset_stats.get(str(best_offset), {}).get("overlap_days", 0))
        payload = {
            "offset_days": int(best_offset),
            "detected_at": now.isoformat(timespec="seconds"),
            "btc_max_diff_pct": float(best_mean_pct) if best_mean_pct is not None else None,
            "btc_overlap_days": overlap_days,
            "method": "btc-close-30d-vs-exchange",
            "exchange": used_exchange,
            "per_offset": per_offset_stats,
        }
        self._persist_cg_offset(payload)
        logger.info(
            "validate_cg_offset: offset_days=%d mean_abs_pct=%s exchange=%s overlap=%d",
            payload["offset_days"],
            payload["btc_max_diff_pct"],
            payload["exchange"],
            overlap_days,
        )
        return payload

    @staticmethod
    def _persist_cg_offset(payload: dict) -> None:
        """Atomic write of cg_offset.json via .tmp + os.replace."""
        import os

        target = _cg_offset_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        # Atomic write helper (no try/except here — LocalStore-style atomic
        # helpers are explicitly allowed; this is the equivalent for the
        # client's own metadata file).
        tmp.write_text(
            _json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, target)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _load_is_excluded(self):
        """
        Lazy-import A2's `is_excluded`. If A2 hasn't landed yet, fall back to a
        pass-through so the rest of the pipeline still runs end-to-end.
        """
        try:
            from backend.data.exclusion import is_excluded  # type: ignore

            return is_excluded
        except Exception as exc:  # noqa: BLE001 - tolerate A2 not ready
            logger.warning(
                "backend.data.exclusion.is_excluded not importable yet (%s) — "
                "falling back to no-op. TODO: A2 wire-up.",
                exc,
            )

            def _passthrough(_coin: dict) -> bool:
                return False

            return _passthrough
