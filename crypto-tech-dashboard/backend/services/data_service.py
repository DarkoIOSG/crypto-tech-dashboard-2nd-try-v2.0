"""Shared in-memory data service for the API routes.

Loads:
    - Postgres (when DATABASE_URL is set, Vercel / GitHub Actions)
    - OR local CSV files (Docker / local dev, no DATABASE_URL)

Provides:
    .list_tokens()                    -> list[dict] of token metadata
    .get_token(cg_id)                 -> dict or None
    .get_ohlcv(cg_id)                 -> pd.DataFrame or None
    .compute_indicators(cg_id, days?) -> dict[str, list of (date, value)]
    .compute_current_indicators(cg_id) -> dict[str, scalar]
    .all_current_indicators()         -> dict[cg_id, dict[indicator, scalar]]
    .current_scores()                 -> dict[cg_id, {trend, reversal, ...}]
    .refresh_from_disk()              -> int  (n tokens loaded)

Hard rule: no try/except in this module — let pandas raise loudly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from backend.config import (
    DATA_DIR,
    DATABASE_URL,
    LAST_UPDATE_PATH,
    MCAP_DIR,
    METADATA_DIR,
    OHLCV_DIR,
    TOP200_CURRENT_PATH,
)

# True when running on Vercel or GitHub Actions with a real Postgres DB.
_USE_DB: bool = bool(DATABASE_URL)
from backend.indicators.registry import INDICATORS
from backend.scoring.ranking import (
    cross_sectional_percentile,
    current_time_series_percentile,
)


SCORES_HISTORY_PATH = MCAP_DIR / "scores_history.csv"
from backend.scoring.reversal_score import (
    REVERSAL_SIGNALS,
    compute_reversal_components,
    cross_sectional_reversal_scores,
)
from backend.scoring.trend_score import (
    TREND_SIGNALS,
    compute_trend_components,
    cross_sectional_trend_scores,
)


def _load_crypto_exclude_set() -> set:
    """Phase 3.5+: read local_data/metadata/crypto_exclude.txt as a set of
    cg_ids to drop from the universe (UI / rankings / cron writes).

    File format: one cg_id per line. Lines starting with '#' are comments,
    blank lines OK. Missing file returns an empty set (no exclusions).
    """
    path = Path(METADATA_DIR) / "crypto_exclude.txt"
    if not path.exists():
        return set()
    try:
        out = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.add(line)
        return out
    except Exception:
        return set()


class DataService:
    """Singleton-style in-memory cache for the API."""

    def __init__(self) -> None:
        self.top_df: Optional[pd.DataFrame] = None
        self.ohlcv_cache: Dict[str, pd.DataFrame] = {}
        self.indicator_cache: Dict[str, Dict[str, pd.Series]] = {}
        self.current_indicators_cache: Dict[str, Dict[str, float]] = {}
        self.scores_cache: Optional[Dict[str, Dict[str, float]]] = None
        self.last_update: Dict = {}
        # P0-D: persisted scores_history.csv loaded lazily, cached as
        # date-indexed wide frames per metric (trend_score, reversal_score)
        # so .score_for() can compute per-token rolling percentiles without
        # re-reading the CSV every request.
        self._scores_history_df: Optional[pd.DataFrame] = None

    # -------------------------------------------------------------- #
    # Loading
    # -------------------------------------------------------------- #
    def refresh_from_disk(self) -> int:
        """Reload token universe + status. Reads from Postgres when DATABASE_URL
        is set; falls back to local CSV files for Docker / local-dev."""
        self.ohlcv_cache.clear()
        self.indicator_cache.clear()
        self.current_indicators_cache.clear()
        self.scores_cache = None
        self._scores_history_df = None
        if hasattr(self, "_stocks_market_cache"):
            self._stocks_market_cache = None

        if _USE_DB:
            return self._refresh_from_db()

        # --- disk path (Docker / local dev) ---
        if Path(TOP200_CURRENT_PATH).exists() and Path(TOP200_CURRENT_PATH).stat().st_size > 0:
            self.top_df = pd.read_csv(TOP200_CURRENT_PATH)
        else:
            self.top_df = None

        if Path(LAST_UPDATE_PATH).exists() and Path(LAST_UPDATE_PATH).stat().st_size > 0:
            raw = Path(LAST_UPDATE_PATH).read_text(encoding="utf-8")
            self.last_update = json.loads(raw) if raw.strip() else {}
        else:
            self.last_update = {}

        return 0 if self.top_df is None else len(self.top_df)

    def _refresh_from_db(self) -> int:
        """Load token universe and metadata from Postgres."""
        from backend.db.postgres_store import PostgresStore
        store = PostgresStore()
        self.top_df = store.read_top200_current()
        self.last_update = store.read_last_update()
        # Pre-warm the scores snapshot cache for fast API reads.
        snap = store.read_scores_snapshot()
        if snap:
            self.scores_cache = snap
        return 0 if self.top_df is None else len(self.top_df)

    # -------------------------------------------------------------- #
    # Token list
    # -------------------------------------------------------------- #
    def list_tokens(self, asset_class: Optional[str] = None) -> List[Dict]:
        """Return list of token metadata.

        R6-17: PLAN sec 11.10 — every cg_id with a CSV on disk gets a row,
        with `active: bool` reflecting Top-N membership.

        R8-1D: every row also carries `asset_class` ∈ {"crypto", "us-stock"}.
        Stocks come from local_data/metadata/stocks_universe.csv; their
        OHLCV CSVs live alongside crypto in local_data/ohlcv/ (uppercase
        filenames vs lowercase cg_ids — no collision in practice). The
        `asset_class` argument, if supplied, filters the output. None
        returns both.
        """
        # First gather what we actually have on disk (or in Postgres).
        if _USE_DB:
            from backend.db.postgres_store import PostgresStore
            on_disk = PostgresStore().get_ohlcv_ids_set()
        else:
            on_disk = set()
            if Path(OHLCV_DIR).exists():
                for p in Path(OHLCV_DIR).glob("*.csv"):
                    if p.name.endswith(".tmp"):
                        continue
                    on_disk.add(p.stem)

        # Phase 3.5+: read the maintained exclude list. Tokens on this list
        # are dropped from the UI / rankings / cron writes — used to retire
        # long-tail tokens whose data source is permanently broken (e.g.
        # hashnote-usyc, 20+ days stale, fails all 8 CCXT + 30-day CG retry).
        # Source-of-truth: local_data/metadata/crypto_exclude.txt (one cg_id
        # per line, # comments).
        exclude_ids = _load_crypto_exclude_set()
        on_disk -= exclude_ids

        # R8-1D: read stocks universe for asset_class metadata.
        stocks_meta: dict = {}  # ticker -> meta row dict
        if _USE_DB:
            from backend.db.postgres_store import PostgresStore
            sdf = PostgresStore().read_stocks_universe()
            if sdf is not None:
                for _, srow in sdf.iterrows():
                    tk = str(srow.get("ticker", "")).strip()
                    if tk:
                        stocks_meta[tk] = {
                            "name": str(srow.get("name") or tk),
                            "exchange": str(srow.get("exchange") or ""),
                            "active": bool(str(srow.get("active", True))),
                        }
        else:
            stocks_path = Path(METADATA_DIR) / "stocks_universe.csv"
            if stocks_path.exists():
                try:
                    sdf = pd.read_csv(stocks_path)
                    for _, srow in sdf.iterrows():
                        tk = str(srow.get("ticker", "")).strip()
                        if tk:
                            stocks_meta[tk] = {
                                "name": str(srow.get("name") or tk),
                                "exchange": str(srow.get("exchange") or ""),
                                "active": bool(str(srow.get("active", "true")).lower() in {"true", "1", "yes"}),
                            }
                except Exception:
                    pass
        stocks_ids = set(stocks_meta.keys())

        out: List[Dict] = []
        active_ids: set = set()
        if self.top_df is not None and len(self.top_df) > 0:
            for _, row in self.top_df.iterrows():
                cg_id = str(row.get("id") or row.get("cg_id") or "")
                if not cg_id:
                    continue
                # Skip stock tickers if they accidentally got into top_df.
                if cg_id in stocks_ids:
                    continue
                # Phase 3.5+: also drop manually-excluded long-tail tokens.
                if cg_id in exclude_ids:
                    continue
                active_ids.add(cg_id)
                has_ohlcv = cg_id in on_disk
                out.append(
                    {
                        "id": cg_id,
                        "asset_class": "crypto",
                        "symbol": str(row.get("symbol") or "").upper(),
                        "name": str(row.get("name") or cg_id),
                        "price": _maybe_float(row.get("current_price")),
                        "mcap": _maybe_float(row.get("market_cap")),
                        # R8-1C: market overview extra columns (Phase-2 item 5).
                        "market_cap_rank": _maybe_float(row.get("market_cap_rank")),
                        "fully_diluted_valuation": _maybe_float(row.get("fully_diluted_valuation")),
                        "total_volume": _maybe_float(row.get("total_volume")),
                        "circulating_supply": _maybe_float(row.get("circulating_supply")),
                        "total_supply": _maybe_float(row.get("total_supply")),
                        "max_supply": _maybe_float(row.get("max_supply")),
                        "price_change_percentage_24h": _maybe_float(row.get("price_change_percentage_24h")),
                        "has_ohlcv": has_ohlcv,
                        "active": True,
                    }
                )
            # R6-17: crypto tokens that exist on disk but no longer in Top-N.
            crypto_inactive = on_disk - active_ids - stocks_ids
            for cg_id in sorted(crypto_inactive):
                out.append(
                    {
                        "id": cg_id,
                        "asset_class": "crypto",
                        "symbol": cg_id.upper(),
                        "name": cg_id,
                        "price": None,
                        "mcap": None,
                        "has_ohlcv": True,
                        "active": False,
                    }
                )
        else:
            for cg_id in sorted(on_disk - stocks_ids):
                out.append(
                    {
                        "id": cg_id,
                        "asset_class": "crypto",
                        "symbol": cg_id.upper(),
                        "name": cg_id,
                        "price": None,
                        "mcap": None,
                        "has_ohlcv": True,
                        "active": True,
                    }
                )

        # R8-1D: append US stocks. Each row in stocks_universe.csv gets a
        # token entry; has_ohlcv reflects whether yfinance pulled it.
        for ticker, meta in sorted(stocks_meta.items()):
            has_ohlcv = ticker in on_disk
            out.append({
                "id": ticker,
                "asset_class": "us-stock",
                "symbol": ticker,
                "name": meta["name"],
                "price": None,             # filled by /api/market_overview
                "mcap": None,
                "exchange": meta.get("exchange", ""),
                "has_ohlcv": has_ohlcv,
                "active": bool(meta.get("active", True)),
            })

        # Optional asset_class filter.
        if asset_class is not None:
            out = [t for t in out if t.get("asset_class") == asset_class]
        return out

    def get_token(self, cg_id: str) -> Optional[Dict]:
        for t in self.list_tokens():
            if t["id"] == cg_id:
                return t
        return None

    # -------------------------------------------------------------- #
    # OHLCV
    # -------------------------------------------------------------- #
    def get_ohlcv(self, cg_id: str) -> Optional[pd.DataFrame]:
        if cg_id in self.ohlcv_cache:
            return self.ohlcv_cache[cg_id]

        if _USE_DB:
            from backend.db.postgres_store import PostgresStore
            df = PostgresStore().read_ohlcv(cg_id)
        else:
            path = Path(OHLCV_DIR) / f"{cg_id}.csv"
            if not path.exists() or path.stat().st_size == 0:
                return None
            df = pd.read_csv(path)

        if df is None or df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        self.ohlcv_cache[cg_id] = df
        return df

    def get_ohlcv_as_records(self, cg_id: str, days: Optional[int] = None) -> List[Dict]:
        """Return OHLCV as a list of dicts (last `days` rows if given)."""
        df = self.get_ohlcv(cg_id)
        if df is None:
            return []
        if days is not None and days > 0:
            df = df.tail(int(days))
        records: List[Dict] = []
        for _, row in df.iterrows():
            records.append(
                {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "open": _maybe_float(row.get("open")),
                    "high": _maybe_float(row.get("high")),
                    "low": _maybe_float(row.get("low")),
                    "close": _maybe_float(row.get("close")),
                    "volume": _maybe_float(row.get("volume")),
                    "source": str(row.get("source") or ""),
                }
            )
        return records

    # -------------------------------------------------------------- #
    # Indicators
    # -------------------------------------------------------------- #
    def _compute_full_indicators(self, cg_id: str) -> Optional[Dict[str, pd.Series]]:
        if cg_id in self.indicator_cache:
            return self.indicator_cache[cg_id]
        df = self.get_ohlcv(cg_id)
        if df is None or len(df) < 30:
            return None
        out: Dict[str, pd.Series] = {}
        for fam in INDICATORS.values():
            produced = fam.compute(df)
            for k, v in produced.items():
                out[k] = v
        self.indicator_cache[cg_id] = out
        return out

    def get_indicators_chart_data(
        self, cg_id: str, days: Optional[int] = None
    ) -> Dict[str, List[Dict]]:
        """Return per-indicator time-series suitable for charts:
            {key: [{date, value}, ...], ...}
        """
        all_ind = self._compute_full_indicators(cg_id)
        if all_ind is None:
            return {}
        df = self.get_ohlcv(cg_id)
        if df is None:
            return {}
        if days is not None and days > 0:
            tail = df.tail(int(days))
            tail_idx = tail.index
        else:
            tail_idx = df.index

        date_series = df["date"].dt.strftime("%Y-%m-%d")
        out: Dict[str, List[Dict]] = {}
        for k, s in all_ind.items():
            series_records: List[Dict] = []
            for i in tail_idx:
                v = s.iloc[i] if i < len(s) else None
                series_records.append(
                    {"date": date_series.iloc[i], "value": _maybe_float(v)}
                )
            out[k] = series_records
        return out

    def compute_current_indicators(self, cg_id: str) -> Dict[str, float]:
        """Last-row scalar values for every indicator key (cached)."""
        if cg_id in self.current_indicators_cache:
            return self.current_indicators_cache[cg_id]
        all_ind = self._compute_full_indicators(cg_id)
        if all_ind is None:
            return {}
        out: Dict[str, float] = {}
        for k, s in all_ind.items():
            if len(s) == 0:
                continue
            out[k] = _maybe_float(s.iloc[-1])
        self.current_indicators_cache[cg_id] = out
        return out

    def all_current_indicators(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for t in self.list_tokens():
            cg_id = t["id"]
            ind = self.compute_current_indicators(cg_id)
            if ind:
                out[cg_id] = ind
        return out

    # -------------------------------------------------------------- #
    # Scoring
    # -------------------------------------------------------------- #
    def current_scores(self) -> Dict[str, Dict[str, float]]:
        """R8-1D: cross-sectional ranking is partitioned by asset_class
        so crypto + stocks DON'T cross-rank (user Q6 "fully separate"). Each
        class gets its own percentile space.
        """
        if self.scores_cache is not None:
            return self.scores_cache

        all_ind = self.all_current_indicators()
        if not all_ind:
            self.scores_cache = {}
            return self.scores_cache

        # Build asset_class lookup once.
        token_to_class = {t["id"]: t.get("asset_class", "crypto") for t in self.list_tokens()}

        # Group indicators by asset_class.
        ind_by_class: Dict[str, Dict[str, Dict[str, float]]] = {}
        for cg_id, ind in all_ind.items():
            ac = token_to_class.get(cg_id, "crypto")
            ind_by_class.setdefault(ac, {})[cg_id] = ind

        # Run scoring + percentile WITHIN each class.
        # R8-2A: Tier-A Overall composite — wires alongside trend/reversal
        # using the same per-class indicators. Each class runs through
        # cross_sectional_overall_scores independently so an alt-coin's
        # vol_20d gets ranked against other crypto, not against MSTR.
        from backend.scoring.overall_score import (
            cross_sectional_overall_scores,
            compute_overall_components,
            cross_sectional_breadth,
            cross_sectional_risk,
        )
        out: Dict[str, Dict[str, float]] = {}
        for ac, class_ind in ind_by_class.items():
            trend_scores = cross_sectional_trend_scores(class_ind)
            reversal_scores = cross_sectional_reversal_scores(class_ind)
            cs_trend = cross_sectional_percentile(trend_scores)
            cs_rev = cross_sectional_percentile(reversal_scores)
            # Components per token (needed for breadth sleeve).
            comps_by_token = {
                cg_id: compute_trend_components(ind)
                for cg_id, ind in class_ind.items()
            }
            # CS-rank the new sleeves so they live on a 0-100 scale.
            breadth_pct = cross_sectional_breadth(comps_by_token)
            risk_pct = cross_sectional_risk(class_ind)
            # R8-2A: TS percentile inputs lazy-computed from scores_history.
            # 2y window only (Plan section says don't backfill scores_history;
            # 3y window is computed but optional).
            ts_trend_by_tok: Dict[str, Optional[float]] = {}
            ts_rev_by_tok: Dict[str, Optional[float]] = {}
            for cg_id in class_ind.keys():
                p = self._token_ts_percentile_pair(cg_id, window_days=730)
                ts_trend_by_tok[cg_id] = p[0]
                ts_rev_by_tok[cg_id] = p[1]
            overall_scores = cross_sectional_overall_scores(
                indicators_by_token=class_ind,
                trend_cs_percentiles=cs_trend,
                reversal_cs_percentiles=cs_rev,
                components_by_token=comps_by_token,
                ts_trend_2y_by_token=ts_trend_by_tok,
                ts_reversal_2y_by_token=ts_rev_by_tok,
            )
            cs_overall = cross_sectional_percentile(overall_scores)

            for cg_id, ind in class_ind.items():
                # Build the 6-row sleeve breakdown for this token.
                sleeve_breakdown = compute_overall_components(
                    trend_cs_pct=float(cs_trend.get(cg_id, 0.0)),
                    reversal_cs_pct=float(cs_rev.get(cg_id, 0.0)),
                    breadth_cs_pct=float(breadth_pct.get(cg_id, 0.0)),
                    risk_cs_pct=float(risk_pct.get(cg_id, 0.0)),
                    ts_trend_2y_pct=ts_trend_by_tok.get(cg_id),
                    ts_reversal_2y_pct=ts_rev_by_tok.get(cg_id),
                )
                out[cg_id] = {
                    "asset_class": ac,
                    "trend_score": float(trend_scores.get(cg_id, 0.0)),
                    "reversal_score": float(reversal_scores.get(cg_id, 0.0)),
                    "trend_cs_percentile": float(cs_trend.get(cg_id, 0.0)),
                    "reversal_cs_percentile": float(cs_rev.get(cg_id, 0.0)),
                    "trend_components": compute_trend_components(ind),
                    "reversal_components": compute_reversal_components(ind),
                    "close_only_data": self._is_close_only_cached(cg_id),
                    # R8-2A new fields
                    "overall_score": float(overall_scores.get(cg_id, 0.0)),
                    "overall_cs_percentile": float(cs_overall.get(cg_id, 0.0)),
                    "overall_components": sleeve_breakdown,
                }
            # R8-2C: rank_in_universe per asset_class (Phase-2 item 1b).
            # Compute three rank dicts via sorted-by-score, then attach to
            # each row. Ranks are 1-indexed; universe_size is len(class).
            universe_size = len(class_ind)
            for score_key, rank_key in [
                ("trend_score", "rank_in_universe_trend"),
                ("reversal_score", "rank_in_universe_reversal"),
                ("overall_score", "rank_in_universe_overall"),
            ]:
                sorted_ids = sorted(
                    class_ind.keys(),
                    key=lambda x: out[x].get(score_key, 0.0),
                    reverse=True,
                )
                for rank, cg_id in enumerate(sorted_ids, start=1):
                    out[cg_id][rank_key] = rank
            for cg_id in class_ind.keys():
                out[cg_id]["universe_size"] = universe_size
        self.scores_cache = out
        return out

    def _token_ts_percentile_pair(self, cg_id: str, window_days: int = 730):
        """Return (trend_ts_pct, reversal_ts_pct) for a token using
        scores_history.csv. (None, None) if history is too short.

        Reused by the Tier-A Overall pipeline. Quick wrapper around
        the existing per-token logic in score_for (which already computes
        these for the legacy 2y/3y percentile fields)."""
        df = self._load_scores_history()
        if df is None or len(df) == 0 or "cg_id" not in df.columns:
            return (None, None)
        sub = df[df["cg_id"] == cg_id]
        if len(sub) < window_days:
            return (None, None)
        from backend.scoring.ranking import current_time_series_percentile
        sub = sub.sort_values("date")
        trend_pct = current_time_series_percentile(sub["trend_score"], window_days)
        rev_pct = current_time_series_percentile(sub["reversal_score"], window_days)
        return (trend_pct, rev_pct)

    def _is_close_only_cached(self, cg_id: str) -> bool:
        """Cheap close-only check off the cached OHLCV frame (no disk re-read).

        Mirrors backend.indicators.base.is_close_only's source-column branch.
        """
        df = self.ohlcv_cache.get(cg_id)
        if df is None or len(df) == 0 or "source" not in df.columns:
            return False
        src = df["source"].astype(str)
        return bool((src == "coingecko").mean() >= 0.5)

    def avg_volume_30d(self, cg_id: str) -> Optional[float]:
        """R8-1C: 30-day rolling average daily volume.

        Reads the latest 30 OHLCV rows from disk (via the cached frame).
        Returns None for tokens whose last 30 days are majority CG-fallback
        (volume is zero-filled there per fetcher._coingecko_close_to_ohlcv);
        showing 0 would be misleading. The UI should render "—" instead.
        """
        df = self.get_ohlcv(cg_id)
        if df is None or len(df) == 0 or "volume" not in df.columns:
            return None
        tail = df.tail(30)
        if "source" in tail.columns:
            fallback_pct = float((tail["source"].astype(str) == "coingecko").mean())
            if fallback_pct >= 0.5:
                return None
        try:
            return float(tail["volume"].astype(float).mean())
        except Exception:
            return None

    def get_market_overview(self, cg_id: str) -> Optional[Dict]:
        """R8-1C: build the "Market Info" payload for /api/market_overview/{id}.

        Pulls mcap_rank + total_volume + supply numbers from list_tokens()
        (sourced from top200_current.csv now that the schema is wider).
        Pulls 30d avg volume from OHLCV. Pulls liquidity source/pair from
        the latest OHLCV row's source column + symbol_map.json.

        Audit P0 (product director + analyst): for asset_class us-stock the
        crypto top200 schema doesn't apply; merge in stocks_market.json
        (refreshed by scripts/refresh_stocks_market.py) so the panel doesn't
        render 4/5 dashes for CRCL / MSTR / COIN etc.
        """
        meta = self.get_token(cg_id)
        if meta is None:
            return None
        df = self.get_ohlcv(cg_id)
        source = None
        if df is not None and len(df) > 0 and "source" in df.columns:
            source = str(df["source"].iloc[-1])

        stock_meta = self._load_stock_market_overview(cg_id) \
            if meta.get("asset_class") == "us-stock" else None

        def _first(*vals):
            for v in vals:
                if v is not None:
                    return v
            return None

        return {
            "cg_id": cg_id,
            "symbol": meta.get("symbol") or cg_id,
            "name": meta.get("name") or (stock_meta or {}).get("name"),
            "current_price": _first(meta.get("price"), (stock_meta or {}).get("current_price")),
            "market_cap": _first(meta.get("mcap"), (stock_meta or {}).get("market_cap")),
            "market_cap_rank": meta.get("market_cap_rank"),
            "fully_diluted_valuation": meta.get("fully_diluted_valuation"),
            "total_volume_24h": _first(meta.get("total_volume"),
                                       (stock_meta or {}).get("total_volume_24h")),
            "avg_volume_30d": self.avg_volume_30d(cg_id),
            "circulating_supply": _first(meta.get("circulating_supply"),
                                         (stock_meta or {}).get("shares_outstanding")),
            "total_supply": meta.get("total_supply"),
            "max_supply": meta.get("max_supply"),
            "price_change_24h_pct": _first(
                meta.get("price_change_percentage_24h"),
                (stock_meta or {}).get("price_change_percentage_24h"),
            ),
            "liquidity": {
                "source_tag": source,
                "exchange": _first((stock_meta or {}).get("exchange"), source),
            },
        }

    def _load_stock_market_overview(self, ticker: str) -> Optional[Dict]:
        """Read per-ticker market data. Source: Postgres metadata or disk JSON."""
        if not hasattr(self, "_stocks_market_cache"):
            self._stocks_market_cache = None
        if self._stocks_market_cache is None:
            if _USE_DB:
                from backend.db.postgres_store import PostgresStore
                val = PostgresStore()._read_metadata("stocks_market")
                self._stocks_market_cache = val if isinstance(val, dict) else {}
            else:
                from pathlib import Path as _P
                path = _P(METADATA_DIR) / "stocks_market.json"
                if not path.exists():
                    self._stocks_market_cache = {}
                else:
                    try:
                        self._stocks_market_cache = json.loads(path.read_text())
                    except Exception:
                        self._stocks_market_cache = {}
        return self._stocks_market_cache.get(ticker)

    def _load_scores_history(self) -> Optional[pd.DataFrame]:
        """Read scores history into a tidy frame. Cached after first call.
        Source: Postgres when DATABASE_URL is set; scores_history.csv otherwise.
        """
        if self._scores_history_df is not None:
            return self._scores_history_df

        if _USE_DB:
            from backend.db.postgres_store import PostgresStore
            df = PostgresStore().read_scores_history()
            if df is None or df.empty:
                self._scores_history_df = pd.DataFrame()
                return self._scores_history_df
            df["date"] = pd.to_datetime(df["date"]).dt.normalize()
            df = df.sort_values(["cg_id", "date"]).reset_index(drop=True)
            self._scores_history_df = df
            return df

        path = Path(SCORES_HISTORY_PATH)
        if not path.exists() or path.stat().st_size == 0:
            self._scores_history_df = pd.DataFrame()
            return self._scores_history_df
        df = pd.read_csv(path)
        if df.empty:
            self._scores_history_df = pd.DataFrame()
            return self._scores_history_df
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.sort_values(["cg_id", "date"]).reset_index(drop=True)
        self._scores_history_df = df
        return df

    def _persisted_history_for(
        self, cg_id: str, column: str
    ) -> pd.Series:
        """Return the persisted per-day Series of `column` for `cg_id`
        (index = date). Empty Series when no rows on disk yet.
        """
        df = self._load_scores_history()
        if df is None or df.empty or column not in df.columns:
            return pd.Series(dtype=float)
        sub = df[df["cg_id"] == cg_id]
        if sub.empty:
            return pd.Series(dtype=float)
        return sub.set_index("date")[column].astype(float).sort_index()

    def scores_monthly_for(self, cg_id: str) -> list:
        """Return monthly overall_score snapshots for one token.

        Groups the daily scores_history by calendar month and takes the last
        recorded score of each month. Returns a list of dicts sorted oldest
        first: [{"month": "YYYY-MM", "score": float}, ...].
        Returns an empty list when no history exists for the token.
        """
        series = self._persisted_history_for(cg_id, "overall_score")
        if series.empty:
            return []
        monthly = (
            series
            .dropna()
            .resample("ME")
            .last()
            .dropna()
        )
        return [
            {"month": idx.strftime("%Y-%m"), "score": round(float(val), 1)}
            for idx, val in monthly.items()
        ]

    def score_for(self, cg_id: str) -> Optional[Dict[str, float]]:
        scores = self.current_scores()
        if cg_id not in scores:
            return None
        base = dict(scores[cg_id])

        # Add 2y / 3y time-series percentiles. We prefer the **persisted**
        # scores_history.csv snapshots (P0-D — daily appends) so the
        # percentile is on the same scale as the live trend_score (a
        # cross-sectional 0..100 rank). When the file is missing or empty
        # on day 0 we fall back to the per-token indicator-mean history we
        # used pre-fix (close enough as a bootstrap until the persisted
        # series accumulates).
        df_hist = self._load_scores_history()
        use_persisted = df_hist is not None and not df_hist.empty
        if use_persisted:
            trend_hist = self._persisted_history_for(cg_id, "trend_score")
            rev_hist = self._persisted_history_for(cg_id, "reversal_score")
        else:
            all_ind = self._compute_full_indicators(cg_id)
            if all_ind is not None:
                trend_hist = self._token_trend_score_history(all_ind)
                rev_hist = self._token_reversal_score_history(all_ind)
            else:
                trend_hist = pd.Series(dtype=float)
                rev_hist = pd.Series(dtype=float)

        # P0-E: a token with fewer OHLCV bars than the lookback window cannot
        # produce a meaningful 2y / 3y time-series percentile — previously
        # `iloc[-730:]` and `iloc[-1095:]` collapsed onto the same short
        # slice and the two percentiles came back identical. We now return
        # None + a data_insufficient_{2y,3y} flag in that case so the
        # frontend can render "data insufficient" instead.
        # The OHLCV row count is the right depth-proxy because it bounds
        # how much score history will ever exist for the token; the
        # persisted scores_history.csv could be sparser early on but its
        # ceiling is the OHLCV depth.
        ohlcv = self.get_ohlcv(cg_id)
        ohlcv_rows = int(len(ohlcv)) if ohlcv is not None else 0

        if ohlcv_rows < 730:
            base["trend_ts_2y_percentile"] = None
            base["reversal_ts_2y_percentile"] = None
            base["data_insufficient_2y"] = True
        else:
            base["trend_ts_2y_percentile"] = current_time_series_percentile(
                trend_hist, 730
            )
            base["reversal_ts_2y_percentile"] = current_time_series_percentile(
                rev_hist, 730
            )
            base["data_insufficient_2y"] = False

        if ohlcv_rows < 1095:
            base["trend_ts_3y_percentile"] = None
            base["reversal_ts_3y_percentile"] = None
            base["data_insufficient_3y"] = True
        else:
            base["trend_ts_3y_percentile"] = current_time_series_percentile(
                trend_hist, 1095
            )
            base["reversal_ts_3y_percentile"] = current_time_series_percentile(
                rev_hist, 1095
            )
            base["data_insufficient_3y"] = False

        return base

    def _token_trend_score_history(
        self, ind: Dict[str, pd.Series]
    ) -> pd.Series:
        """Build a per-day raw trend score series for one token.

        We use the **equal-weighted average of signed signal values** (not the
        cross-sectional percentile — that requires the full universe). This is
        good enough for the historical percentile read-out.
        """
        cols = []
        for sig in TREND_SIGNALS:
            s = ind.get(sig)
            if s is not None:
                cols.append(s.rename(sig))
        if not cols:
            return pd.Series(dtype=float)
        frame = pd.concat(cols, axis=1).fillna(0)
        return frame.mean(axis=1)

    def _token_reversal_score_history(
        self, ind: Dict[str, pd.Series]
    ) -> pd.Series:
        cols = []
        for key, sign in REVERSAL_SIGNALS:
            s = ind.get(key)
            if s is None:
                continue
            cols.append((s * sign).rename(key))
        if not cols:
            return pd.Series(dtype=float)
        frame = pd.concat(cols, axis=1).fillna(0)
        return frame.mean(axis=1)


def _maybe_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float):
        return value if value == value else None  # NaN -> None
    if isinstance(value, (int,)):
        return float(value)
    # pandas / numpy scalar
    f = pd.to_numeric(value, errors="coerce")
    if f is None:
        return None
    if hasattr(f, "item"):
        v = float(f)
        return v if v == v else None
    return None


# Module-level singleton — bound in main.py at startup.
_SERVICE: Optional[DataService] = None


def get_service() -> DataService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DataService()
        _SERVICE.refresh_from_disk()
    return _SERVICE


def set_service(svc: DataService) -> None:
    global _SERVICE
    _SERVICE = svc
