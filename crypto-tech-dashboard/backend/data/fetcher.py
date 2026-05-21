"""
backend/data/fetcher.py
========================

Orchestration layer that wires together the CoinGecko / multi-exchange clients,
the symbol mapper, and the local CSV cache to perform:

  1. `run_full_initial_load()` — first-time pull of Top-N universe + 3 years of
     daily OHLCV per token (with multi-exchange waterfall and CoinGecko close-
     price fallback).
  2. `run_daily_update()` — incremental append of the last few days of OHLCV
     per stored token, plus a fresh Top-N snapshot.
  3. `update_market_cap_snapshot()` — convenience helper for refreshing only
     `top200_current.csv` and the daily mcap snapshot.

Hard rule (A1 dispatch): NO try/except in this module. All external-API and
filesystem error handling lives inside the wrapper modules (exchange_client,
coingecko_client, local_store). This module relies on those wrappers returning
None / empty DataFrames on failure.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from backend.config import (
    BACKUP_KEEP,
    COINGECKO_SOURCE_TAG,
    DATA_DIR,
    HISTORY_DAYS,
    TOP_N,
    UPDATE_TIMEZONE,
)

log = logging.getLogger(__name__)


def _snapshot_current_scores_for_history(store) -> pd.DataFrame:
    """Compute today's per-token (trend, reversal) scores + cross-sectional
    percentiles from the on-disk OHLCV cache and return a DataFrame with
    the canonical scores_history.csv shape.

    Returns an empty DataFrame when no OHLCV files are present.
    """
    # Local imports to avoid circular references at module-import time.
    from backend.indicators.registry import INDICATORS  # noqa: WPS433
    from backend.scoring.reversal_score import (  # noqa: WPS433
        cross_sectional_reversal_scores,
    )
    from backend.scoring.trend_score import (  # noqa: WPS433
        cross_sectional_trend_scores,
    )
    from backend.scoring.ranking import cross_sectional_percentile  # noqa: WPS433

    cg_ids = store.list_ohlcv_ids()
    if not cg_ids:
        return pd.DataFrame(columns=[
            "cg_id", "trend_score", "reversal_score",
            "trend_cs_percentile", "reversal_cs_percentile",
        ])

    all_current: Dict[str, Dict[str, float]] = {}
    skipped: list = []
    for cg_id in cg_ids:
        # P1-E: per-token isolation. A single malformed CSV (e.g.
        # KeyError on `low`, value-type mismatch) used to bring down the
        # whole daily snapshot — zero rows persisted. This try/except is
        # the only allowed exception in this file outside the P1-C
        # status-integrity finally blocks: it lives at the daily-batch
        # boundary inside _snapshot_current_scores_for_history (NOT the
        # outermost fetcher method) and is the documented isolation
        # pattern from the hard-rules. We log+skip the failing cg_id
        # and continue with the other 199 tokens.
        try:
            df = store.read_ohlcv(cg_id)
            if df is None or len(df) < 30:
                continue
            current: Dict[str, float] = {}
            for fam in INDICATORS.values():
                produced = fam.compute(df)
                for k, s in produced.items():
                    if len(s) == 0:
                        continue
                    v = s.iloc[-1]
                    # Coerce numpy/pandas scalar to float; treat NaN as missing.
                    v = float(v) if v == v else None
                    if v is not None:
                        current[k] = v
            if current:
                all_current[cg_id] = current
        except Exception as exc:  # noqa: BLE001 - per-token isolation
            log.warning(
                "scores_history snapshot: skipping %s (%s: %s)",
                cg_id,
                type(exc).__name__,
                exc,
            )
            skipped.append(cg_id)
    if skipped:
        log.warning(
            "scores_history snapshot: skipped %d / %d tokens due to errors",
            len(skipped),
            len(cg_ids),
        )

    if not all_current:
        return pd.DataFrame(columns=[
            "cg_id", "trend_score", "reversal_score",
            "trend_cs_percentile", "reversal_cs_percentile",
        ])

    trend = cross_sectional_trend_scores(all_current)
    reversal = cross_sectional_reversal_scores(all_current)
    cs_trend = cross_sectional_percentile(trend)
    cs_rev = cross_sectional_percentile(reversal)

    # R8-2A: also persist the Tier-A Overall composite + its CS percentile
    # so the history table can drive future Tier-B regressions and the UI's
    # "rank in universe by overall_score" lookup. Plan R8-2A acceptance.
    from backend.scoring.overall_score import (  # noqa: WPS433
        cross_sectional_overall_scores,
    )
    from backend.scoring.trend_score import compute_trend_components  # noqa: WPS433

    components_by_token = {
        cg_id: compute_trend_components(ind) for cg_id, ind in all_current.items()
    }
    overall = cross_sectional_overall_scores(
        indicators_by_token=all_current,
        trend_cs_percentiles=cs_trend,
        reversal_cs_percentiles=cs_rev,
        components_by_token=components_by_token,
        # TS-2y sleeves left as None for offline snapshots — the live scoring
        # path passes them; downstream compute_overall_score treats None as
        # 50.0 (neutral) so older snapshots stay comparable.
    )
    cs_overall = cross_sectional_percentile(overall)

    rows = []
    for cg_id in all_current:
        rows.append({
            "cg_id": cg_id,
            "trend_score": float(trend.get(cg_id, 0.0)),
            "reversal_score": float(reversal.get(cg_id, 0.0)),
            "trend_cs_percentile": float(cs_trend.get(cg_id, 0.0)),
            "reversal_cs_percentile": float(cs_rev.get(cg_id, 0.0)),
            "overall_score": float(overall.get(cg_id, 0.0)),
            "overall_cs_percentile": float(cs_overall.get(cg_id, 0.0)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Columns expected by `LocalStore.write_ohlcv` (date, open, high, low, close,
# volume; `source` is added by the store from the `source` kwarg).
_OHLCV_PRICE_COLS: List[str] = ["open", "high", "low", "close", "volume"]


def _load_stock_tickers() -> set:
    """Audit P0: helper used by run_daily_update to exclude stocks from the
    crypto cron loop. Reads stocks_universe.csv if present; returns a set
    of ticker symbols (uppercase). Returns empty set on any failure — the
    crypto cron then degrades to its prior behaviour of "iterate everything"
    rather than crashing on a parse error.
    """
    try:
        from pathlib import Path as _P
        import pandas as _pd
        path = _P(DATA_DIR) / "metadata" / "stocks_universe.csv"
        if not path.exists():
            return set()
        df = _pd.read_csv(path)
        if "ticker" not in df.columns:
            return set()
        return {str(t).strip() for t in df["ticker"].dropna()}
    except Exception:  # boundary
        return set()


def _now_iso_local() -> str:
    """Return current local time as ISO-8601 string (no tzinfo coupling)."""
    return _dt.datetime.now().isoformat(timespec="seconds")


def _coingecko_close_to_ohlcv(df_close: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce a CoinGecko close-price DataFrame (columns: date, close) into the
    canonical OHLCV shape expected by `LocalStore.write_ohlcv`.

    Open/High/Low are filled with the close value (degenerate single-point
    bar) so downstream indicators that read O/H/L still get *something*
    finite. Volume is set to 0. Callers tag `source="coingecko"` so the UI
    can flag these tokens as close-price-only.
    """
    if df_close is None or df_close.empty:
        return pd.DataFrame(columns=["date"] + _OHLCV_PRICE_COLS)
    out = df_close.copy()
    # CoinGecko gives only close; mirror it onto O/H/L for a degenerate bar.
    out["open"] = out["close"]
    out["high"] = out["close"]
    out["low"] = out["close"]
    out["volume"] = 0.0
    return out[["date"] + _OHLCV_PRICE_COLS]


def _build_mcap_snapshot(top_df: pd.DataFrame) -> pd.DataFrame:
    """Project the Top-N markets DataFrame down to the snapshot columns."""
    if top_df is None or top_df.empty:
        return pd.DataFrame(columns=["cg_id", "mcap"])
    cols_in = top_df.columns
    snap = pd.DataFrame()
    snap["cg_id"] = top_df["id"] if "id" in cols_in else top_df.get("cg_id")
    snap["mcap"] = top_df["market_cap"] if "market_cap" in cols_in else top_df.get("mcap")
    return snap.dropna(subset=["cg_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class Fetcher:
    """
    High-level data orchestration.

    Dependencies are passed in (constructor injection) so this class is
    trivially unit-testable with fakes.
    """

    def __init__(
        self,
        exchange_client,
        coingecko_client,
        mapper,
        store,
        validator=None,
    ):
        self.exchange_client = exchange_client
        self.coingecko_client = coingecko_client
        self.mapper = mapper
        self.store = store
        # Validator is optional — wired in if/when the sibling module lands.
        self.validator = validator
        # Phase 3.1: in-memory refresh progress, polled by the frontend
        # progress bar.
        self._progress = {
            "phase": "idle",   # idle | crypto | crypto_retry | stocks
            "current": 0,
            "total": 0,
            "last_token": None,
            "started_at": None,
            "finished_at": None,
        }
        # P0-2 (architect audit): explicit in-flight lock. The earlier claim
        # "daily-update is never run concurrently" was false — three entry
        # points can race (manual /api/system/refresh via FastAPI BackgroundTasks,
        # the APScheduler hourly_self_heal job, and the boot-refresh thread).
        # A concurrent read-modify-write of last_update.json by two of them
        # silently clobbers the other's result. The lock is non-reentrant
        # and acquired non-blocking so the second caller fast-returns
        # status="skipped" instead of queueing.
        import threading as _threading
        self._refresh_lock = _threading.Lock()

    def _progress_set(self, phase=None, current=None, total=None, last_token=None,
                      started_at=None, finished_at=None):
        """Helper to update only the named keys without dropping the rest."""
        p = self._progress
        if phase is not None:       p["phase"] = phase
        if current is not None:     p["current"] = current
        if total is not None:       p["total"] = total
        if last_token is not None:  p["last_token"] = last_token
        if started_at is not None:  p["started_at"] = started_at
        if finished_at is not None: p["finished_at"] = finished_at

    # ------------------------------------------------------------------ #
    # Full initial load
    # ------------------------------------------------------------------ #
    def run_full_initial_load(
        self,
        top_n: int = TOP_N,
        history_days: int = HISTORY_DAYS,
    ) -> Dict:
        """
        First-time bulk pull. Steps:

          A. CoinGecko `/coins/markets` -> Top-N (with exclusion filter already
             applied inside `fetch_top_n_markets`).
          B. `load_markets_all()` on all exchanges so the SymbolMapper can do a
             pure lookup.
          C. `mapper.discover()` over the Top-N universe (populates / updates
             `symbol_map.json`).
          D. Per token: `exchange_client.fetch_ohlcv_waterfall` -> on None,
             fall back to `coingecko_client.fetch_close_price_history`.
          E. Persist `top200_current.csv` + today's `mcap_daily/<iso>.csv`.
          F. Update `last_update.json` with timestamps and counters.

        Returns a summary dict:
            {
              "status": "ok",
              "top_n": int, "history_days": int,
              "universe_size": int,
              "success": int, "fallback": int, "failed": int,
              "failed_ids": list[str],
              "started_at": iso, "finished_at": iso,
            }
        """
        started_at = _now_iso_local()
        log.info(
            "run_full_initial_load: starting top_n=%d history_days=%d",
            top_n,
            history_days,
        )

        # P1-C: status-integrity guard. Without this, an uncaught exception
        # anywhere in the body skips _write_last_update() entirely, leaving
        # the prior status="ok" in place. The UI then serves stale data
        # with no failure signal. We use a single try/finally — the ONLY
        # such block in this module — at the fetcher's outer boundary.
        # NOTE: no `except` clause, only `finally` (we WANT the original
        # traceback to propagate to the caller / scheduler / logs). This
        # is the minimum surface a contextmanager / status-flag pattern
        # would need anyway (we still have to update on-disk state on the
        # error path), so `try/finally` is the most honest expression.
        _completed = {"ok": False}
        try:
            # ---- A. Fetch Top-N universe from CoinGecko ----
            top_df = self.coingecko_client.fetch_top_n_markets(n=top_n)
            if top_df is None or top_df.empty:
                log.error("run_full_initial_load: CoinGecko returned empty universe")
                summary = {
                    "status": "error",
                    "error_detail": "coingecko universe empty",
                    "top_n": int(top_n),
                    "history_days": int(history_days),
                    "universe_size": 0,
                    "success": 0,
                    "fallback": 0,
                    "failed": 0,
                    "failed_ids": [],
                    "started_at": started_at,
                    "finished_at": _now_iso_local(),
                }
                self._write_last_update(summary, full_load=True)
                _completed["ok"] = True
                return summary

            universe_size = len(top_df)
            log.info("run_full_initial_load: universe_size=%d", universe_size)

            # ---- B. Warm exchange `load_markets()` caches ----
            # P0-H: force a refresh of the cache rather than reusing whatever
            # state survives from the last boot (where Binance is 451 and the
            # cached None can stick around forever).
            for _name in list(self.exchange_client._markets_cache.keys()):  # noqa: SLF001
                self.exchange_client._markets_cache[_name] = None  # noqa: SLF001
            self.exchange_client._markets_loaded = False  # noqa: SLF001
            markets_cache = self.exchange_client.load_markets_all()

            # P0-H: health-gate same as run_daily_update — refuse to silently
            # tank the run to 100% CG-fallback when every exchange is down.
            n_alive = sum(
                1 for m in markets_cache.values() if m is not None and len(m) > 0
            )
            if n_alive == 0:
                summary = {
                    "status": "error",
                    "error_detail": "all 4 exchanges unreachable; refusing 100% CG fallback",
                    "top_n": int(top_n),
                    "history_days": int(history_days),
                    "universe_size": int(universe_size),
                    "success": 0,
                    "fallback": 0,
                    "failed": 0,
                    "failed_ids": [],
                    "started_at": started_at,
                    "finished_at": _now_iso_local(),
                }
                log.error("run_full_initial_load: %s", summary["error_detail"])
                self._write_last_update(summary, full_load=True)
                _completed["ok"] = True
                return summary

            # ---- C. Discover symbols across all 4 exchanges ----
            # Pass dicts so the mapper can use coin["symbol"] as the base ticker.
            coin_dicts = top_df[["id", "symbol"]].to_dict(orient="records")
            self.mapper.discover(coin_dicts)

            # ---- C.5: P0-M backup current ohlcv/ before overwriting ----
            # PLAN sec3.2 step 5 mandates a pre-overwrite snapshot of the
            # OHLCV cache so a botched waterfall can be rolled back. We snap
            # to ohlcv_backup_YYYYMMDD/ then prune older backups beyond
            # BACKUP_KEEP. Snapshotting is idempotent within the same day.
            backup_path = self.store.snapshot_ohlcv_backup()
            if backup_path is not None:
                log.info("run_full_initial_load: snapshot -> %s", backup_path)
                removed = self.store.prune_ohlcv_backups(BACKUP_KEEP)
                if removed:
                    log.info(
                        "run_full_initial_load: pruned %d old backup dir(s) (keep=%d)",
                        removed,
                        BACKUP_KEEP,
                    )

            # ---- D. Per-token OHLCV waterfall + fallback ----
            success = 0
            fallback = 0
            failed = 0
            failed_ids: List[str] = []

            for row in top_df.itertuples(index=False):
                cg_id = getattr(row, "id", None)
                if not cg_id:
                    continue

                df, source = self.exchange_client.fetch_ohlcv_waterfall(
                    cg_id=cg_id, days=history_days, mapper=self.mapper
                )

                if df is not None and not df.empty:
                    self.store.write_ohlcv(cg_id, df, source)
                    success += 1
                    continue

                # CoinGecko close-price fallback.
                log.info("run_full_initial_load: %s falling back to coingecko", cg_id)
                df_close = self.coingecko_client.fetch_close_price_history(
                    cg_id=cg_id, days=history_days
                )
                if df_close is not None and not df_close.empty:
                    df_full = _coingecko_close_to_ohlcv(df_close)
                    if not df_full.empty:
                        self.store.write_ohlcv(cg_id, df_full, COINGECKO_SOURCE_TAG)
                        fallback += 1
                        continue

                failed += 1
                failed_ids.append(cg_id)
                log.warning("run_full_initial_load: %s — ALL sources failed", cg_id)

            # ---- E. Snapshot files ----
            self.store.write_top200_current(top_df)
            today = _dt.date.today()
            self.store.write_mcap_snapshot(today, _build_mcap_snapshot(top_df))

            finished_at = _now_iso_local()
            summary = {
                "status": "ok",
                "top_n": int(top_n),
                "history_days": int(history_days),
                "universe_size": int(universe_size),
                "success": int(success),
                "fallback": int(fallback),
                "failed": int(failed),
                "failed_ids": failed_ids,
                "started_at": started_at,
                "finished_at": finished_at,
            }
            log.info(
                "run_full_initial_load: done success=%d fallback=%d failed=%d",
                success,
                fallback,
                failed,
            )

            # ---- F. last_update.json ----
            self._write_last_update(summary, full_load=True)
            _completed["ok"] = True

            # ---- G. scores_history.csv (P0-G Option A): full backfill ----
            # Previously this only appended today's snapshot. That made the
            # 2y / 3y time-series percentile collapse to 100.0 for every
            # long-history token (rank-of-one). On a full initial load we now
            # rebuild the entire history from each token's OHLCV — the score
            # is a closed-form function of OHLCV, so backfill is deterministic.
            self._backfill_scores_history()

            # Optional integrity validation if validator is wired in.
            self._maybe_run_validator()

            return summary
        finally:
            # P1-C: if the try-block raised before we managed to write
            # last_update.json (status=ok), record status=error here so
            # the API and UI surface the failure instead of serving stale
            # status="ok". Idempotent on the success path.
            if not _completed["ok"]:
                err_summary = {
                    "status": "error",
                    "error_detail": "run_full_initial_load crashed before completion",
                    "top_n": int(top_n),
                    "history_days": int(history_days),
                    "universe_size": 0,
                    "success": 0,
                    "fallback": 0,
                    "failed": 0,
                    "failed_ids": [],
                    "started_at": started_at,
                    "finished_at": _now_iso_local(),
                }
                self._write_last_update(err_summary, full_load=True)

    # ------------------------------------------------------------------ #
    # Daily incremental update
    # ------------------------------------------------------------------ #
    def run_daily_update(self) -> Dict:
        """
        Per existing cg_id in `ohlcv/`:
          - waterfall-fetch the last ~5 days
          - `store.append_ohlcv` (dedupe by date)
        Also refresh `top200_current.csv` and write today's mcap snapshot.

        Returns:
            {"status": "ok", "tokens": int, "rows_appended": int,
             "fallback": int, "failed": int, "failed_ids": list[str],
             "universe_size": int, "started_at": iso, "finished_at": iso}
        """
        # P0-2: fast-skip if another refresh is already in flight.
        if not self._refresh_lock.acquire(blocking=False):
            log.info("run_daily_update: skipped — another refresh already running")
            return {"status": "skipped", "reason": "already_running"}
        started_at = _now_iso_local()
        log.info("run_daily_update: starting")

        # P1-C: status-integrity guard — see P1-C comment on
        # run_full_initial_load above for the rationale. try/finally only
        # (no `except`); we want the original exception to propagate.
        _completed = {"ok": False}
        # P0-O: new-token cold-start tracking, surfaced in the summary so
        # the operator sees how many Top-N entrants were back-filled today.
        new_arrivals: List[str] = []
        try:
            # ---- P0-O: cold-start newly-arrived Top-N tokens BEFORE the
            # per-existing-CSV walk. Previously run_daily_update only
            # iterated tokens already present in ohlcv/; a fresh Top-N
            # entrant would never get an OHLCV file until the next full
            # reload. We now refresh the universe early, detect new cg_ids,
            # discover their exchange symbols, and pull HISTORY_DAYS for
            # each one via the same waterfall used by run_full_initial_load.
            top_df_for_arrivals = self.coingecko_client.fetch_top_n_markets(n=TOP_N)
            if top_df_for_arrivals is not None and not top_df_for_arrivals.empty:
                # Audit P0: exclude stocks from "existing crypto" set so a
                # crypto cg_id matching a stock ticker by coincidence does
                # the wrong thing. Stocks are managed by run_stocks_*.
                _stock_tickers_for_arrivals = _load_stock_tickers()
                existing = set(self.store.list_ohlcv_ids()) - _stock_tickers_for_arrivals
                universe_ids = [
                    str(x)
                    for x in top_df_for_arrivals["id"].dropna().tolist()
                    if str(x)
                ]
                new_arrivals = [cid for cid in universe_ids if cid not in existing]
                if new_arrivals:
                    log.info(
                        "run_daily_update: %d new Top-N arrival(s): %s",
                        len(new_arrivals),
                        new_arrivals[:10],
                    )
                    # Refresh symbol mapper for the arrivals (and the rest
                    # of the universe — discover is idempotent and cheap).
                    arrival_dicts = top_df_for_arrivals[
                        top_df_for_arrivals["id"].isin(new_arrivals)
                    ][["id", "symbol"]].to_dict(orient="records")
                    self.mapper.discover(arrival_dicts)
                    # Per-arrival waterfall + CG fallback, mirroring the
                    # full-load body. We use HISTORY_DAYS so the new token
                    # is immediately comparable to the rest of the universe.
                    for cg_id in new_arrivals:
                        df_new, source_new = self.exchange_client.fetch_ohlcv_waterfall(
                            cg_id=cg_id, days=HISTORY_DAYS, mapper=self.mapper
                        )
                        if df_new is not None and not df_new.empty:
                            self.store.write_ohlcv(cg_id, df_new, source_new)
                            log.info(
                                "run_daily_update: cold-start %s via %s rows=%d",
                                cg_id,
                                source_new,
                                len(df_new),
                            )
                            continue
                        df_cg = self.coingecko_client.fetch_close_price_history(
                            cg_id=cg_id, days=HISTORY_DAYS
                        )
                        if df_cg is not None and not df_cg.empty:
                            df_full = _coingecko_close_to_ohlcv(df_cg)
                            if not df_full.empty:
                                self.store.write_ohlcv(
                                    cg_id, df_full, COINGECKO_SOURCE_TAG
                                )
                                log.info(
                                    "run_daily_update: cold-start %s via coingecko rows=%d",
                                    cg_id,
                                    len(df_full),
                                )
                                continue
                        log.warning(
                            "run_daily_update: cold-start %s FAILED — no source returned data",
                            cg_id,
                        )

            # Audit P0: crypto cron MUST NOT iterate over stock tickers — they
            # have a separate cron (run_stocks_daily_update via yfinance) and
            # CCXT / CoinGecko don't know what MSTR is, so every stock would
            # land in failed_ids and poison last_run_summary. Filter them out.
            all_ids = self.store.list_ohlcv_ids()
            stock_tickers = _load_stock_tickers()
            cg_ids = [i for i in all_ids if i not in stock_tickers]
            if not cg_ids:
                log.warning(
                    "run_daily_update: no ohlcv files found — run_full_initial_load first"
                )

            # Warm market caches so the mapper lookup is hot.
            # P0-H: force re-load every refresh so a transient outage on the
            # previous boot doesn't permanently pin the cache to None and push
            # every token to the CG-close-only fallback path.
            for _name in list(self.exchange_client._markets_cache.keys()):  # noqa: SLF001
                self.exchange_client._markets_cache[_name] = None  # noqa: SLF001
            self.exchange_client._markets_loaded = False  # noqa: SLF001
            markets_cache = self.exchange_client.load_markets_all()

            # P0-H health-gate: if every exchange's markets dict is empty,
            # this run would silently go 100% CG-fallback. Return an explicit
            # error so the UI can surface "exchanges unreachable" rather than
            # the old behaviour where status=ok and fallback=universe_size.
            n_alive = sum(
                1 for m in markets_cache.values() if m is not None and len(m) > 0
            )
            if n_alive == 0:
                finished_at = _now_iso_local()
                summary = {
                    "status": "error",
                    "error_detail": "all 4 exchanges unreachable; refusing 100% CG fallback",
                    "tokens": len(cg_ids),
                    "rows_appended": 0,
                    "fallback": 0,
                    "failed": 0,
                    "failed_ids": [],
                    "universe_size": 0,
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
                log.error("run_daily_update: %s", summary["error_detail"])
                self._write_last_update(summary, full_load=False)
                _completed["ok"] = True
                return summary

            rows_appended = 0
            fallback = 0
            failed = 0
            failed_ids: List[str] = []
            recovered_ids: List[str] = []   # R7-8: tokens that the retry pass salvaged
            # Phase 3 Module 3: dynamic lookback. 7-day baseline covers a
            # long-weekend / Mon-holiday gap (architect audit: 5 was a hair
            # tight for 3-day weekends + Monday US holiday). If the host
            # was off longer (last_ohlcv_update >= 7 days old), the
            # expand-clamp logic below bumps lookback up to 30.
            lookback_days = 7
            try:
                existing = self.store.read_last_update() or {}
                last_iso = existing.get("last_ohlcv_update")
                if last_iso:
                    last_dt = _dt.datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
                    if last_dt.tzinfo is None:
                        gap = (_dt.datetime.now() - last_dt).days
                    else:
                        gap = (_dt.datetime.now(last_dt.tzinfo) - last_dt).days
                    if gap > 3:
                        lookback_days = min(gap + 2, 30)
                        log.info(
                            "run_daily_update: detected %d-day gap, expanding "
                            "lookback to %d days", gap, lookback_days,
                        )
            except Exception:  # boundary, last-update parsing
                pass

            # Phase 3.1: progress bar — primary crypto pass.
            self._progress_set(phase="crypto", current=0, total=len(cg_ids),
                               last_token=None, started_at=started_at,
                               finished_at=None)
            for i, cg_id in enumerate(cg_ids, start=1):
                self._progress_set(current=i, last_token=cg_id)
                df, source = self.exchange_client.fetch_ohlcv_waterfall(
                    cg_id=cg_id, days=lookback_days, mapper=self.mapper
                )

                if df is not None and not df.empty:
                    df_to_append = df.copy()
                    df_to_append["source"] = source
                    added = self.store.append_ohlcv(cg_id, df_to_append)
                    rows_appended += int(added)
                    continue

                # CoinGecko fallback for tokens not on any exchange.
                df_close = self.coingecko_client.fetch_close_price_history(
                    cg_id=cg_id, days=lookback_days
                )
                if df_close is not None and not df_close.empty:
                    df_full = _coingecko_close_to_ohlcv(df_close)
                    if not df_full.empty:
                        df_full["source"] = COINGECKO_SOURCE_TAG
                        added = self.store.append_ohlcv(cg_id, df_full)
                        rows_appended += int(added)
                        fallback += 1
                        continue

                failed_ids.append(cg_id)
                log.warning("run_daily_update: %s — all sources failed in primary pass", cg_id)

            # R7-8: single retry pass on failed_ids with a longer lookback
            # window (30 days). Rationale: PLAN sec 11.10 says transient API
            # errors should be retried with backoff; the primary loop has 5-
            # day lookback so a token that's been silent for 6-29 days appears
            # "all sources failed" when really the data is fetchable but past
            # the primary window. The retry uses CG-only since the exchange
            # waterfall already failed at primary; CG has more graceful
            # multi-day coverage. hashnote-usyc was the Round-7 P1-1 case:
            # 13 days stale, still tracked in failed_ids without anybody
            # ever trying a deeper pull.
            still_failed: List[str] = []
            if failed_ids:
                retry_lookback = 30
                log.info(
                    "run_daily_update: retrying %d failed_ids with %d-day lookback",
                    len(failed_ids), retry_lookback,
                )
                # Phase 3.1: progress bar — retry pass.
                self._progress_set(phase="crypto_retry", current=0,
                                   total=len(failed_ids), last_token=None)
                for ri, cg_id in enumerate(failed_ids, start=1):
                    self._progress_set(current=ri, last_token=cg_id)
                    df_close = self.coingecko_client.fetch_close_price_history(
                        cg_id=cg_id, days=retry_lookback
                    )
                    if df_close is not None and not df_close.empty:
                        df_full = _coingecko_close_to_ohlcv(df_close)
                        if not df_full.empty:
                            df_full["source"] = COINGECKO_SOURCE_TAG
                            added = self.store.append_ohlcv(cg_id, df_full)
                            rows_appended += int(added)
                            fallback += 1
                            recovered_ids.append(cg_id)
                            log.info(
                                "run_daily_update: recovered %s via 30-day CG retry",
                                cg_id,
                            )
                            continue
                    still_failed.append(cg_id)
                    log.warning(
                        "run_daily_update: %s — still failing after retry",
                        cg_id,
                    )
            # Replace the primary failed_ids with the post-retry residue so
            # the summary surfaces the *actually unrecoverable* tokens, and
            # update the failed counter accordingly.
            failed_ids = still_failed
            failed = len(failed_ids)

            # Refresh universe + market-cap snapshot.
            universe_size = self.update_market_cap_snapshot()

            finished_at = _now_iso_local()
            # Phase 3.7 (final architect P1-1): explicit `success` counter
            # so operators reading /api/system/status get a clean
            # breakdown instead of having to compute tokens − failed −
            # fallback themselves. success = tokens that wrote at least
            # one new row via Tier-1 exchange waterfall.
            success_count = len(cg_ids) - failed - fallback
            summary = {
                "status": "ok",
                "tokens": len(cg_ids),
                "success": int(success_count),
                "rows_appended": int(rows_appended),
                "fallback": int(fallback),
                "failed": int(failed),
                "failed_ids": failed_ids,
                # R7-8: separately surface the recovered set so the operator
                # can see "today's CG-deep-retry salvaged N tokens".
                "recovered_ids": list(recovered_ids),
                "universe_size": int(universe_size) if universe_size is not None else 0,
                # P0-O: surface the cold-started new arrivals so the operator
                # can correlate "today's universe size grew by N" with the
                # exact cg_ids that came in.
                "new_arrivals": list(new_arrivals),
                "started_at": started_at,
                "finished_at": finished_at,
            }
            log.info(
                "run_daily_update: done tokens=%d rows_appended=%d failed=%d "
                "recovered=%d new_arrivals=%d",
                len(cg_ids),
                rows_appended,
                failed,
                len(recovered_ids),
                len(new_arrivals),
            )

            self._write_last_update(summary, full_load=False)
            _completed["ok"] = True
            # P0-D: append today's score snapshot to scores_history.csv.
            self._append_scores_history_snapshot(_dt.date.today())
            self._maybe_run_validator()
            # Phase 3.2 critical (architect audit): invalidate the in-memory
            # DataService caches so the next /api/scores, /api/indicators,
            # /api/rankings request lazy-recomputes from the freshly-written
            # OHLCV CSVs. Without this, run_daily_update would write today's
            # bars to disk but the live API kept serving yesterday's scores
            # until container restart — silently breaking the "all formulas
            # recompute" promise.
            try:
                from backend.services.data_service import get_service
                get_service().refresh_from_disk()
                log.info("run_daily_update: invalidated DataService caches")
            except Exception as exc:  # boundary: cache invalidation never fatal
                log.warning("run_daily_update: cache invalidate failed: %s", exc)
            # Phase 3.1: progress bar — mark complete.
            self._progress_set(phase="idle", current=0, total=0,
                               last_token=None, finished_at=finished_at)
            return summary
        finally:
            # P1-C: if anything above raised before _write_last_update,
            # persist a status=error record so /api/system/status reflects
            # the failure rather than leaving the prior status="ok".
            if not _completed["ok"]:
                err_summary = {
                    "status": "error",
                    "error_detail": "run_daily_update crashed before completion",
                    "tokens": 0,
                    "rows_appended": 0,
                    "fallback": 0,
                    "failed": 0,
                    "failed_ids": [],
                    "universe_size": 0,
                    "started_at": started_at,
                    "finished_at": _now_iso_local(),
                }
                self._write_last_update(err_summary, full_load=False)
            # P0-3 (architect audit): always reset the progress dict, even on
            # crash. Without this the UI would keep showing "crypto 147/210"
            # forever after a failed refresh, and the auto-poller would
            # interpret phase != "idle" as still in flight.
            self._progress_set(phase="idle", current=0, total=0,
                               last_token=None,
                               finished_at=_now_iso_local())
            # P0-2: release the in-flight lock no matter what.
            try:
                self._refresh_lock.release()
            except RuntimeError:
                pass   # already released (shouldn't happen, defensive)

    # ------------------------------------------------------------------ #
    # Market-cap-only refresh
    # ------------------------------------------------------------------ #
    def update_market_cap_snapshot(self) -> Optional[int]:
        """
        Refresh `top200_current.csv` and write today's `mcap_daily/<iso>.csv`.

        Returns the universe size written, or None on total failure.
        """
        top_df = self.coingecko_client.fetch_top_n_markets(n=TOP_N)
        if top_df is None or top_df.empty:
            log.warning("update_market_cap_snapshot: empty top_n from CoinGecko")
            return None

        # Phase 3.5+: drop manually-excluded long-tail tokens before persisting
        # so the next cron iteration also skips them. Without this, the
        # exclude list would filter UI/rankings but the cron would still
        # keep fetching them every 24 h.
        try:
            from backend.services.data_service import _load_crypto_exclude_set
            exclude_ids = _load_crypto_exclude_set()
            if exclude_ids:
                before = len(top_df)
                id_col = "id" if "id" in top_df.columns else "cg_id"
                top_df = top_df[~top_df[id_col].isin(exclude_ids)].reset_index(drop=True)
                dropped = before - len(top_df)
                if dropped > 0:
                    log.info("update_market_cap_snapshot: dropped %d excluded "
                             "ids from universe (%s)", dropped, sorted(exclude_ids))
        except Exception as exc:  # boundary: exclude is non-critical
            log.warning("update_market_cap_snapshot: exclude filter failed: %s", exc)

        self.store.write_top200_current(top_df)
        today = _dt.date.today()
        self.store.write_mcap_snapshot(today, _build_mcap_snapshot(top_df))
        log.info(
            "update_market_cap_snapshot: wrote universe of %d on %s",
            len(top_df),
            today.isoformat(),
        )
        return len(top_df)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _write_last_update(self, summary: Dict, full_load: bool) -> None:
        """Merge `summary` into `last_update.json` (read-modify-write)."""
        existing = self.store.read_last_update()
        if not isinstance(existing, dict):
            existing = {}

        now_iso = summary.get("finished_at") or _now_iso_local()
        existing["last_ohlcv_update"] = now_iso
        existing["last_mcap_update"] = now_iso
        existing["status"] = summary.get("status", "idle")
        existing["timezone"] = UPDATE_TIMEZONE
        existing["mode"] = "full_load" if full_load else "daily_update"
        existing["last_run_summary"] = summary
        self.store.write_last_update(existing)

    def _append_scores_history_snapshot(self, date: _dt.date) -> None:
        """Compute today's per-token scores from the on-disk OHLCV cache and
        append them to scores_history.csv.

        Pure book-keeping — used by run_full_initial_load and
        run_daily_update at their tails. Failures inside the scoring step
        should not crash the fetcher; the snapshot routine itself just
        returns an empty frame in that case (no try/except needed because
        all upstream pieces are exception-free per the hard rules).
        """
        snapshot = _snapshot_current_scores_for_history(self.store)
        if snapshot is None or snapshot.empty:
            log.warning(
                "scores_history snapshot: empty (no scored tokens); skipping append"
            )
            return
        n_rows = self.store.append_scores_history(date, snapshot)
        log.info(
            "scores_history snapshot: appended %d rows for %s", n_rows, date.isoformat()
        )

    def _backfill_scores_history(self) -> None:
        """P0-G Option A: rebuild scores_history.csv from each token's
        full OHLCV history.

        Delegates to `scripts.backfill_scores_history.backfill` so the
        same logic powers both the operator-facing one-shot script and
        the full-load tail. The script lives outside `backend/` and is
        intentionally a no-dependency module.
        """
        # Lazy import to keep this method cost-free unless invoked.
        from pathlib import Path  # noqa: WPS433
        import importlib.util  # noqa: WPS433

        # scripts/ lives next to backend/ under <project>/crypto-tech-dashboard.
        backend_dir = Path(__file__).resolve().parent.parent
        script_path = backend_dir.parent / "scripts" / "backfill_scores_history.py"
        if not script_path.exists():
            log.warning(
                "_backfill_scores_history: %s missing; skipping backfill",
                script_path,
            )
            return
        spec = importlib.util.spec_from_file_location(
            "_backfill_scores_history_module", script_path
        )
        if spec is None or spec.loader is None:
            log.warning("_backfill_scores_history: failed to build import spec")
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        n_rows = module.backfill(self.store.data_dir)
        log.info("_backfill_scores_history: wrote %d rows", n_rows)

    def _maybe_run_validator(self) -> None:
        """
        If a validator is wired in (or available lazily), let it write its
        integrity log. We import lazily to keep this module importable even
        when the parallel A1c agent hasn't shipped yet.
        """
        validator = self.validator
        if validator is None:
            # Lazy import attempt — purely best-effort, returns silently when
            # the module isn't on disk yet.
            import importlib.util

            spec = importlib.util.find_spec("backend.data.data_validator")
            if spec is None:
                return
            module = importlib.import_module("backend.data.data_validator")
            factory = getattr(module, "DataValidator", None)
            if factory is None:
                return
            validator = factory(self.store)

        run = getattr(validator, "run", None)
        if callable(run):
            run()

    # ------------------------------------------------------------------ #
    # R8-1A: single-token repair path used by the admin /api/admin/repair
    # endpoint and the integrity check's quarantine recovery.
    # ------------------------------------------------------------------ #
    def repair_token(self, cg_id: str, *, history_days: int = HISTORY_DAYS) -> Dict:
        """Re-fetch a single token via the full waterfall and rewrite its CSV.

        Use case: a CSV got quarantined by the boot integrity check, or an
        operator noticed a single token went stale. This calls the same
        exchange-waterfall + CG-fallback path as run_full_initial_load but
        only for one token, so it is fast and idempotent.

        Returns a summary dict {cg_id, source, rows, status}.
        """
        log.info("repair_token: %s — refetching %d days", cg_id, history_days)
        # Try the exchange waterfall first.
        df, source = self.exchange_client.fetch_ohlcv_waterfall(
            cg_id=cg_id, days=history_days, mapper=self.mapper
        )
        if df is not None and not df.empty:
            self.store.write_ohlcv(cg_id, df, source)
            log.info("repair_token: %s — restored via %s (%d rows)", cg_id, source, len(df))
            return {
                "cg_id": cg_id,
                "source": source,
                "rows": int(len(df)),
                "status": "ok",
            }

        # Fall back to CoinGecko close-only.
        df_close = self.coingecko_client.fetch_close_price_history(
            cg_id=cg_id, days=history_days
        )
        if df_close is not None and not df_close.empty:
            df_full = _coingecko_close_to_ohlcv(df_close)
            if not df_full.empty:
                self.store.write_ohlcv(cg_id, df_full, COINGECKO_SOURCE_TAG)
                log.info(
                    "repair_token: %s — restored via coingecko close-only (%d rows)",
                    cg_id, len(df_full),
                )
                return {
                    "cg_id": cg_id,
                    "source": COINGECKO_SOURCE_TAG,
                    "rows": int(len(df_full)),
                    "status": "ok",
                }

        log.warning("repair_token: %s — ALL sources failed", cg_id)
        return {
            "cg_id": cg_id,
            "source": None,
            "rows": 0,
            "status": "failed",
        }

    # ------------------------------------------------------------------ #
    # R8-1B.2: history extension to 2020-01-01 + data_coverage metadata.
    # Phase-2 item 11. Strategy: re-pull each token with the wide
    # HISTORY_DAYS window, then build data_coverage.json from the resulting
    # CSV's source distribution.
    # ------------------------------------------------------------------ #
    def run_history_extension(
        self,
        target_start_date: str = "2020-01-01",
    ) -> Dict:
        """Extend every OHLCV CSV backward to target_start_date.

        Implementation: run_full_initial_load with a calculated history_days
        wide enough to reach target_start_date. The full_initial_load path
        already (a) snapshots to ohlcv_backup_YYYYMMDD/ before overwriting
        and (b) walks the 8-exchange waterfall + CG fallback. For tokens
        that listed AFTER target_start_date, the waterfall stops at listing
        date — that's correct per Phase-2 item 11.2 ("for tokens that listed
        after 2020, fetch from the listing day onward").
        """
        today = _dt.date.today()
        target_dt = _dt.date.fromisoformat(target_start_date)
        history_days = (today - target_dt).days
        log.info(
            "run_history_extension: target=%s requires history_days=%d "
            "(current HISTORY_DAYS config=%d)",
            target_start_date, history_days, HISTORY_DAYS,
        )
        summary = self.run_full_initial_load(
            top_n=TOP_N, history_days=history_days,
        )
        coverage = self.update_data_coverage()
        summary["coverage_tokens_updated"] = len(coverage)
        summary["target_start_date"] = target_start_date
        summary["history_days_used"] = history_days
        return summary

    def _compute_data_coverage(self, cg_id: str) -> Optional[Dict]:
        """Build a per-token coverage record from its CSV's source distribution.

        Schema:
          {
            "earliest_date": "YYYY-MM-DD",
            "latest_date":   "YYYY-MM-DD",
            "real_ohlc_from": "YYYY-MM-DD" | None,  # first non-CG row
            "close_only_windows": [["from","to"], ...],
            "tier_breakdown": [
              {"from": "...", "to": "...", "tier": 1|4, "source": "...", "rows": N}, ...
            ],
            "n_rows": int,
          }
        """
        df = self.store.read_ohlcv(cg_id)
        if df is None or len(df) == 0:
            return None
        df = df.sort_values("date").reset_index(drop=True)

        date_str = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        earliest = str(date_str.iloc[0])
        latest = str(date_str.iloc[-1])

        tier_breakdown: List[Dict] = []
        close_only_windows: List[List[str]] = []
        real_ohlc_from: Optional[str] = None

        if "source" in df.columns:
            # Group consecutive rows by source value.
            sources = df["source"].astype(str)
            run_id = (sources != sources.shift()).cumsum()
            for _gid, group_idx in df.groupby(run_id).groups.items():
                group = df.loc[group_idx]
                src = str(group["source"].iloc[0])
                from_d = str(date_str.iloc[group.index[0]])
                to_d = str(date_str.iloc[group.index[-1]])
                tier = 4 if src == COINGECKO_SOURCE_TAG else 1
                tier_breakdown.append({
                    "from": from_d,
                    "to": to_d,
                    "tier": tier,
                    "source": src,
                    "rows": int(len(group)),
                })
                if tier == 4:
                    close_only_windows.append([from_d, to_d])
            # First non-coingecko row
            non_cg = df[sources != COINGECKO_SOURCE_TAG]
            if len(non_cg) > 0:
                real_ohlc_from = str(date_str.iloc[non_cg.index[0]])

        return {
            "earliest_date": earliest,
            "latest_date": latest,
            "real_ohlc_from": real_ohlc_from,
            "close_only_windows": close_only_windows,
            "tier_breakdown": tier_breakdown,
            "n_rows": int(len(df)),
        }

    def update_data_coverage(self, cg_ids: Optional[List[str]] = None) -> Dict:
        """Write/refresh local_data/metadata/data_coverage.json.

        Called at the tail of run_history_extension and run_daily_update.
        Reads every OHLCV CSV (or just the listed cg_ids), computes the
        per-token coverage record via _compute_data_coverage, atomically
        writes the dict to disk.
        """
        coverage_path = Path(DATA_DIR) / "metadata" / "data_coverage.json"
        coverage_path.parent.mkdir(parents=True, exist_ok=True)

        existing: Dict = {}
        if coverage_path.exists():
            raw = coverage_path.read_text()
            if raw.strip():
                existing = _json.loads(raw)

        ids = cg_ids if cg_ids is not None else self.store.list_ohlcv_ids()
        for cg_id in ids:
            cov = self._compute_data_coverage(cg_id)
            if cov is not None:
                existing[cg_id] = cov

        tmp = coverage_path.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(existing, indent=2, sort_keys=True))
        tmp.replace(coverage_path)
        log.info("update_data_coverage: wrote %s (%d tokens)",
                 coverage_path, len(existing))
        return existing

    # ------------------------------------------------------------------ #
    # R8-1D: US stocks daily/cold-load via yfinance.
    # Phase-2 item 7. Mirrors run_full_initial_load but uses yfinance
    # instead of CCXT, and operates on the stocks_universe.csv config.
    # ------------------------------------------------------------------ #
    def run_stocks_load(
        self,
        *,
        history_days: int = HISTORY_DAYS,
        client=None,
        universe_csv=None,
    ) -> Dict:
        """Fetch OHLCV for every active row in stocks_universe.csv via
        yfinance. Writes to local_data/ohlcv/{TICKER}.csv with source tag
        "yfinance". Same atomic-write + dedup semantics as the crypto path.
        """
        from pathlib import Path as _Path
        from backend.data.yfinance_client import (
            YFinanceClient, load_stocks_universe, STOCKS_SOURCE_TAG,
        )

        if universe_csv is None:
            universe_csv = _Path(DATA_DIR) / "metadata" / "stocks_universe.csv"
        if not _Path(universe_csv).exists():
            log.warning("run_stocks_load: %s not found, nothing to do", universe_csv)
            return {"status": "ok", "tokens": 0, "success": 0, "failed": 0,
                    "failed_ids": []}

        client = client or YFinanceClient()
        universe = load_stocks_universe(universe_csv)
        active = universe[universe["active"]] if "active" in universe.columns else universe

        success = 0
        failed_ids: List[str] = []
        started_at = _now_iso_local()
        log.info(
            "run_stocks_load: %d active tickers, %d days each",
            len(active), history_days,
        )
        for row in active.itertuples(index=False):
            ticker = str(getattr(row, "ticker", "")).strip()
            if not ticker:
                continue
            df = client.fetch_ohlcv(ticker, days=history_days)
            if df is None or df.empty:
                failed_ids.append(ticker)
                log.warning("run_stocks_load: %s — no data", ticker)
                continue
            # write_ohlcv normalises the columns + atomically writes.
            self.store.write_ohlcv(ticker, df, STOCKS_SOURCE_TAG)
            success += 1
        finished_at = _now_iso_local()
        summary = {
            "status": "ok",
            "asset_class": "us-stock",
            "tokens": int(len(active)),
            "success": int(success),
            "failed": int(len(failed_ids)),
            "failed_ids": failed_ids,
            "started_at": started_at,
            "finished_at": finished_at,
        }
        log.info("run_stocks_load: done success=%d failed=%d",
                 success, len(failed_ids))
        return summary

    def run_stocks_daily_update(self) -> Dict:
        """Daily incremental refresh for stocks — 5-day lookback per
        ticker, dedup-by-date append. Mirrors run_daily_update for crypto."""
        # P0-2: shared in-flight lock with run_daily_update so the two
        # don't race on last_update.json. Different keys ("last_run_summary"
        # vs "last_stocks_summary") but same file — read-modify-write.
        if not self._refresh_lock.acquire(blocking=False):
            log.info("run_stocks_daily_update: skipped — another refresh already running")
            return {"status": "skipped", "reason": "already_running"}
        # Phase 3.5 (final audit P1-B2): mirror the crypto path's
        # status-integrity guard. Previously a crash before line 1296
        # (e.g. inside load_stocks_universe or DataFrame iteration) left
        # the prior successful last_stocks_update timestamp in place; the
        # hourly self-heal then read it as "fresh" and skipped recovery
        # for 24 h. Track completion explicitly so a crash gets a visible
        # status="error" record.
        _stocks_completed = {"ok": False}
        _stocks_started_at = _now_iso_local()
        # Phase 3.7 (final architect audit P0-2): yfinance import + the
        # whole body MUST be inside the try block so the finally branch
        # always releases the lock and resets progress. Previously the
        # `from backend.data.yfinance_client import …` sat between
        # acquire and try — if the import itself raised (package
        # corruption, dependency missing, sys.path weirdness) the lock
        # would stay held forever and require container restart. Also
        # adds a single retry-after-2s on import failure (modelled after
        # the user's v3 production yf helper's RETRY_MAX pattern, but
        # collapsed to a single retry — the second attempt is cheap and
        # catches transient import races, not permanent breakage).
        # P0-3: try/finally so any yfinance crash still resets the progress
        # bar and releases the lock.
        try:
            try:
                from backend.data.yfinance_client import (
                    YFinanceClient, load_stocks_universe, STOCKS_SOURCE_TAG,
                )
            except Exception as imp_exc:  # noqa: BLE001
                log.warning("run_stocks_daily_update: yfinance import "
                            "failed (%s) — retrying in 2 s", imp_exc)
                import time as _t_retry
                _t_retry.sleep(2)
                try:
                    from backend.data.yfinance_client import (
                        YFinanceClient, load_stocks_universe, STOCKS_SOURCE_TAG,
                    )
                except Exception as imp_exc2:  # noqa: BLE001
                    log.error("run_stocks_daily_update: yfinance import "
                              "failed twice — bailing: %s", imp_exc2)
                    return {"status": "error",
                            "asset_class": "us-stock",
                            "error_detail": f"yfinance import failed: {imp_exc2}",
                            "tokens": 0, "rows_appended": 0,
                            "failed_ids": [],
                            "started_at": _stocks_started_at,
                            "finished_at": _now_iso_local()}
            universe_csv = Path(DATA_DIR) / "metadata" / "stocks_universe.csv"
            if not universe_csv.exists():
                return {"status": "ok", "tokens": 0, "rows_appended": 0,
                        "failed_ids": []}
            client = YFinanceClient()
            universe = load_stocks_universe(universe_csv)
            active = universe[universe["active"]] if "active" in universe.columns else universe

            lookback_days = 7   # 5 trading days + weekend cushion
            rows_appended = 0
            failed_ids: List[str] = []
            started_at = _now_iso_local()
            # Phase 3.1: progress bar — stocks pass.
            active_rows = list(active.itertuples(index=False))
            self._progress_set(phase="stocks", current=0, total=len(active_rows),
                               last_token=None, started_at=started_at,
                               finished_at=None)
            for si, row in enumerate(active_rows, start=1):
                ticker = str(getattr(row, "ticker", "")).strip()
                if not ticker:
                    continue
                self._progress_set(current=si, last_token=ticker)
                # P1 (architect audit): per-ticker try/except so one yfinance
                # ConnectionError doesn't kill the whole stocks pass.
                try:
                    df = client.fetch_ohlcv(ticker, days=lookback_days)
                except Exception as exc:  # boundary: yfinance flakey
                    log.warning("run_stocks_daily_update: %s fetch failed: %s",
                                ticker, exc)
                    failed_ids.append(ticker)
                    continue
                if df is None or df.empty:
                    failed_ids.append(ticker)
                    continue
                added = self.store.append_ohlcv(ticker, df)
                rows_appended += int(added)
            finished_at = _now_iso_local()
            # Phase 3.7 (P1-1): symmetric `success` counter so the stocks
            # summary in /api/system/status reads the same way as crypto.
            stocks_success = int(len(active)) - int(len(failed_ids))
            summary = {
                "status": "ok",
                "asset_class": "us-stock",
                "tokens": int(len(active)),
                "success": stocks_success,
                "rows_appended": int(rows_appended),
                "failed": int(len(failed_ids)),
                "failed_ids": failed_ids,
                "started_at": started_at,
                "finished_at": finished_at,
            }
            # Audit P0: refresh stocks fundamentals (mcap / 24h volume / etc.)
            # alongside the OHLCV append.
            try:
                from pathlib import Path as _P
                import json as _json, time as _t
                out = {}
                for row in active.itertuples(index=False):
                    ticker = str(getattr(row, "ticker", "")).strip()
                    if not ticker:
                        continue
                    out[ticker] = client.fetch_market_overview(ticker)
                out["_refreshed_at"] = _t.strftime("%Y-%m-%dT%H:%M:%S")
                mkt_path = _P(DATA_DIR) / "metadata" / "stocks_market.json"
                tmp = mkt_path.with_suffix(".json.tmp")
                tmp.write_text(_json.dumps(out, indent=2))
                tmp.replace(mkt_path)
                log.info("run_stocks_daily_update: refreshed market overview for %d tickers", len(out)-1)
            except Exception as exc:  # boundary: yfinance .info often flakey
                log.warning("run_stocks_daily_update: market overview refresh failed: %s", exc)

            log.info("run_stocks_daily_update: appended=%d failed=%d",
                     rows_appended, len(failed_ids))
            # Audit P0: also persist a stocks-scoped summary into last_update.json
            try:
                existing = self.store.read_last_update() or {}
                if not isinstance(existing, dict):
                    existing = {}
                existing["last_stocks_summary"] = summary
                existing["last_stocks_update"] = finished_at
                self.store.write_last_update(existing)
            except Exception as exc:  # boundary
                log.warning("run_stocks_daily_update: persist last_update failed: %s", exc)
            # Phase 3.2 critical (architect audit): same cache invalidation
            # as run_daily_update. Without this, /api/scores?asset_class=us-stock
            # and /api/market_overview/{ticker} keep returning yesterday's
            # numbers until container restart.
            try:
                from backend.services.data_service import get_service
                get_service().refresh_from_disk()
                log.info("run_stocks_daily_update: invalidated DataService caches")
            except Exception as exc:  # boundary
                log.warning("run_stocks_daily_update: cache invalidate failed: %s", exc)
            _stocks_completed["ok"] = True
            return summary
        finally:
            # Phase 3.5 (P1-B2): if anything above raised before we wrote
            # the success summary, persist an error record so the hourly
            # self-heal's "last_stocks_update" gap check actually trips
            # next round. Without this the previous good timestamp stays
            # in place and stocks-only failures hide for 24 h.
            if not _stocks_completed["ok"]:
                try:
                    existing = self.store.read_last_update() or {}
                    if not isinstance(existing, dict):
                        existing = {}
                    existing["last_stocks_summary"] = {
                        "status": "error",
                        "asset_class": "us-stock",
                        "error_detail": "run_stocks_daily_update crashed before completion",
                        "started_at": _stocks_started_at,
                        "finished_at": _now_iso_local(),
                    }
                    # Deliberately do NOT advance last_stocks_update — leaving
                    # it at the prior good value means the gap check at
                    # main.py self-heal will compute a real (growing) gap and
                    # re-trigger on the next :30 after the 4-h cooldown.
                    self.store.write_last_update(existing)
                except Exception as exc:  # boundary
                    log.warning("run_stocks_daily_update: error-record persist failed: %s", exc)
            # P0-3: always reset progress (even on crash) so the UI doesn't
            # stick on "US Stocks 18/38" forever.
            self._progress_set(phase="idle", current=0, total=0,
                               last_token=None,
                               finished_at=_now_iso_local())
            # P0-2: release the lock.
            try:
                self._refresh_lock.release()
            except RuntimeError:
                pass
