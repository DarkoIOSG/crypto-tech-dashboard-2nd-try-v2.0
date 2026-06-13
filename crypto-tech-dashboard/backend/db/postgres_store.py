"""Postgres-backed implementation of the LocalStore interface.

Drop-in replacement for backend/data/local_store.py when DATABASE_URL is set.
The Fetcher and DataService use this instead of CSV files when running on
Vercel (API reads) or in GitHub Actions (daily writes).

Interface contract — every method mirrors LocalStore exactly so callers
(Fetcher, DataService) need zero changes when switching backends.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Dict, List, Optional

import pandas as pd
import psycopg2.extras

from backend.db.connection import get_conn

log = logging.getLogger("backend.db.postgres_store")


class PostgresStore:
    """Postgres-backed store. Stateless: opens a connection per operation."""

    # ------------------------------------------------------------------ #
    # OHLCV
    # ------------------------------------------------------------------ #

    def read_ohlcv(self, cg_id: str) -> Optional[pd.DataFrame]:
        """Return full OHLCV history for cg_id as a DataFrame, or None."""
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    """
                    SELECT date, open, high, low, close, volume, source
                    FROM ohlcv
                    WHERE cg_id = %s
                    ORDER BY date
                    """,
                    (cg_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "source"])
        df["date"] = pd.to_datetime(df["date"])
        return df

    def write_ohlcv(self, cg_id: str, df: pd.DataFrame, source: str) -> None:
        """Atomic full-replace of OHLCV data for cg_id."""
        if df is None or df.empty:
            return
        out = df.copy()
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        out["source"] = source
        out = out.drop_duplicates(subset=["date"], keep="last").sort_values("date")

        rows = [
            (
                cg_id,
                row["date"],
                _safe_float(row.get("open")),
                _safe_float(row.get("high")),
                _safe_float(row.get("low")),
                _safe_float(row.get("close")),
                _safe_float(row.get("volume")),
                str(row.get("source") or source),
            )
            for _, row in out.iterrows()
        ]

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ohlcv WHERE cg_id = %s", (cg_id,))
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO ohlcv (cg_id, date, open, high, low, close, volume, source)
                    VALUES %s
                    ON CONFLICT (cg_id, date) DO UPDATE
                        SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                            close=EXCLUDED.close, volume=EXCLUDED.volume, source=EXCLUDED.source
                    """,
                    rows,
                    page_size=500,
                )
            conn.commit()
        finally:
            conn.close()

    def append_ohlcv(self, cg_id: str, new_rows: pd.DataFrame) -> int:
        """Upsert new OHLCV rows for cg_id. Returns count of rows inserted/updated."""
        if new_rows is None or new_rows.empty:
            return 0

        incoming = new_rows.copy()
        incoming["date"] = pd.to_datetime(incoming["date"]).dt.strftime("%Y-%m-%d")
        if "source" not in incoming.columns:
            incoming["source"] = ""

        rows = [
            (
                cg_id,
                row["date"],
                _safe_float(row.get("open")),
                _safe_float(row.get("high")),
                _safe_float(row.get("low")),
                _safe_float(row.get("close")),
                _safe_float(row.get("volume")),
                str(row.get("source") or ""),
            )
            for _, row in incoming.iterrows()
        ]

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO ohlcv (cg_id, date, open, high, low, close, volume, source)
                    VALUES %s
                    ON CONFLICT (cg_id, date) DO UPDATE
                        SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                            close=EXCLUDED.close, volume=EXCLUDED.volume, source=EXCLUDED.source
                    """,
                    rows,
                    page_size=500,
                )
                n = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        return max(n, 0)

    def list_ohlcv_ids(self) -> List[str]:
        """Return sorted list of cg_ids that have OHLCV data."""
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT cg_id FROM ohlcv ORDER BY cg_id")
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def get_ohlcv_ids_set(self) -> set:
        return set(self.list_ohlcv_ids())

    # ------------------------------------------------------------------ #
    # Token universe (replaces top200_current.csv)
    # ------------------------------------------------------------------ #

    def write_top200_current(self, df: pd.DataFrame) -> None:
        """Upsert top-200 crypto token metadata into the tokens table."""
        if df is None or df.empty:
            return

        rows = []
        for _, row in df.iterrows():
            cg_id = str(row.get("id") or row.get("cg_id") or "")
            if not cg_id:
                continue
            rows.append((
                cg_id,
                str(row.get("symbol") or "").upper(),
                str(row.get("name") or cg_id),
                "crypto",
                _safe_float(row.get("current_price")),
                _safe_float(row.get("market_cap")),
                _safe_int(row.get("market_cap_rank")),
                _safe_float(row.get("fully_diluted_valuation")),
                _safe_float(row.get("total_volume")),
                _safe_float(row.get("circulating_supply")),
                _safe_float(row.get("total_supply")),
                _safe_float(row.get("max_supply")),
                _safe_float(row.get("price_change_percentage_24h")),
                True,
            ))

        if not rows:
            return

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO tokens (
                        cg_id, symbol, name, asset_class,
                        current_price, market_cap, market_cap_rank,
                        fully_diluted_valuation, total_volume,
                        circulating_supply, total_supply, max_supply,
                        price_change_percentage_24h, active, updated_at
                    ) VALUES %s
                    ON CONFLICT (cg_id) DO UPDATE SET
                        symbol=EXCLUDED.symbol, name=EXCLUDED.name,
                        current_price=EXCLUDED.current_price,
                        market_cap=EXCLUDED.market_cap,
                        market_cap_rank=EXCLUDED.market_cap_rank,
                        fully_diluted_valuation=EXCLUDED.fully_diluted_valuation,
                        total_volume=EXCLUDED.total_volume,
                        circulating_supply=EXCLUDED.circulating_supply,
                        total_supply=EXCLUDED.total_supply,
                        max_supply=EXCLUDED.max_supply,
                        price_change_percentage_24h=EXCLUDED.price_change_percentage_24h,
                        active=EXCLUDED.active,
                        updated_at=NOW()
                    """,
                    rows,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
                    page_size=250,
                )
            conn.commit()
        finally:
            conn.close()

    def read_top200_current(self) -> Optional[pd.DataFrame]:
        """Return crypto tokens as a DataFrame with CoinGecko-compatible columns."""
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        cg_id AS id,
                        symbol, name, asset_class,
                        current_price, market_cap, market_cap_rank,
                        fully_diluted_valuation, total_volume,
                        circulating_supply, total_supply, max_supply,
                        price_change_percentage_24h, active
                    FROM tokens
                    WHERE asset_class = 'crypto'
                    ORDER BY market_cap_rank NULLS LAST
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows])
        if df.empty:
            return None
        return df

    # ------------------------------------------------------------------ #
    # Scores history (replaces scores_history.csv)
    # ------------------------------------------------------------------ #

    def append_scores_history(self, date, df_scores: pd.DataFrame) -> int:
        """Upsert a daily score snapshot into scores_history."""
        if df_scores is None or df_scores.empty:
            return 0

        if isinstance(date, _dt.datetime):
            iso = date.date().isoformat()
        elif isinstance(date, _dt.date):
            iso = date.isoformat()
        else:
            iso = pd.to_datetime(str(date)).date().isoformat()

        _COLS = [
            "cg_id", "trend_score", "reversal_score",
            "trend_cs_percentile", "reversal_cs_percentile",
            "overall_score", "overall_cs_percentile",
        ]
        incoming = df_scores.copy()
        for col in _COLS[1:]:
            if col not in incoming.columns:
                incoming[col] = None

        rows = [
            (
                str(row.get("cg_id", "")),
                iso,
                _safe_float(row.get("trend_score")),
                _safe_float(row.get("reversal_score")),
                _safe_float(row.get("trend_cs_percentile")),
                _safe_float(row.get("reversal_cs_percentile")),
                _safe_float(row.get("overall_score")),
                _safe_float(row.get("overall_cs_percentile")),
            )
            for _, row in incoming.iterrows()
            if str(row.get("cg_id", ""))
        ]

        if not rows:
            return 0

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO scores_history
                        (cg_id, date, trend_score, reversal_score,
                         trend_cs_percentile, reversal_cs_percentile,
                         overall_score, overall_cs_percentile)
                    VALUES %s
                    ON CONFLICT (cg_id, date) DO UPDATE SET
                        trend_score=EXCLUDED.trend_score,
                        reversal_score=EXCLUDED.reversal_score,
                        trend_cs_percentile=EXCLUDED.trend_cs_percentile,
                        reversal_cs_percentile=EXCLUDED.reversal_cs_percentile,
                        overall_score=EXCLUDED.overall_score,
                        overall_cs_percentile=EXCLUDED.overall_cs_percentile
                    """,
                    rows,
                    page_size=300,
                )
            conn.commit()
        finally:
            conn.close()

        return len(rows)

    def read_scores_history(self) -> Optional[pd.DataFrame]:
        """Return scores_history as a tidy DataFrame."""
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    """
                    SELECT cg_id, date, trend_score, reversal_score,
                           trend_cs_percentile, reversal_cs_percentile,
                           overall_score, overall_cs_percentile
                    FROM scores_history
                    ORDER BY date, cg_id
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        return df

    # ------------------------------------------------------------------ #
    # Scores snapshot (pre-computed current scores for fast API reads)
    # ------------------------------------------------------------------ #

    def write_scores_snapshot(self, scores: Dict[str, Dict]) -> None:
        """Persist pre-computed current scores so the API avoids recomputing
        all 240+ indicator sets on every cold start."""
        if not scores:
            return

        rows = []
        for cg_id, s in scores.items():
            rows.append((
                cg_id,
                str(s.get("asset_class") or "crypto"),
                _safe_float(s.get("trend_score")),
                _safe_float(s.get("reversal_score")),
                _safe_float(s.get("trend_cs_percentile")),
                _safe_float(s.get("reversal_cs_percentile")),
                _safe_float(s.get("overall_score")),
                _safe_float(s.get("overall_cs_percentile")),
                _safe_int(s.get("rank_in_universe_trend")),
                _safe_int(s.get("rank_in_universe_reversal")),
                _safe_int(s.get("rank_in_universe_overall")),
                _safe_int(s.get("universe_size")),
                bool(s.get("close_only_data", False)),
                json.dumps(s.get("trend_components") or {}),
                json.dumps(s.get("reversal_components") or {}),
                json.dumps(s.get("overall_components") or {}),
            ))

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO scores_snapshot (
                        cg_id, asset_class,
                        trend_score, reversal_score,
                        trend_cs_percentile, reversal_cs_percentile,
                        overall_score, overall_cs_percentile,
                        rank_in_universe_trend, rank_in_universe_reversal, rank_in_universe_overall,
                        universe_size, close_only_data,
                        trend_components, reversal_components, overall_components,
                        updated_at
                    ) VALUES %s
                    ON CONFLICT (cg_id) DO UPDATE SET
                        asset_class=EXCLUDED.asset_class,
                        trend_score=EXCLUDED.trend_score,
                        reversal_score=EXCLUDED.reversal_score,
                        trend_cs_percentile=EXCLUDED.trend_cs_percentile,
                        reversal_cs_percentile=EXCLUDED.reversal_cs_percentile,
                        overall_score=EXCLUDED.overall_score,
                        overall_cs_percentile=EXCLUDED.overall_cs_percentile,
                        rank_in_universe_trend=EXCLUDED.rank_in_universe_trend,
                        rank_in_universe_reversal=EXCLUDED.rank_in_universe_reversal,
                        rank_in_universe_overall=EXCLUDED.rank_in_universe_overall,
                        universe_size=EXCLUDED.universe_size,
                        close_only_data=EXCLUDED.close_only_data,
                        trend_components=EXCLUDED.trend_components,
                        reversal_components=EXCLUDED.reversal_components,
                        overall_components=EXCLUDED.overall_components,
                        updated_at=NOW()
                    """,
                    rows,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,NOW())",
                    page_size=300,
                )
            conn.commit()
        finally:
            conn.close()

    def read_scores_snapshot(self) -> Optional[Dict[str, Dict]]:
        """Read the pre-computed scores snapshot. Returns None if empty."""
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM scores_snapshot")
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return None
        out = {}
        for r in rows:
            d = dict(r)
            cg_id = d.pop("cg_id")
            # Deserialize JSONB columns (psycopg2 returns them as dicts already)
            for col in ("trend_components", "reversal_components", "overall_components"):
                if isinstance(d.get(col), str):
                    d[col] = json.loads(d[col])
            out[cg_id] = d
        return out

    # ------------------------------------------------------------------ #
    # Metadata (replaces last_update.json and other JSON metadata files)
    # ------------------------------------------------------------------ #

    def read_last_update(self) -> Dict:
        """Read the last_update metadata entry."""
        val = self._read_metadata("last_update")
        return val if isinstance(val, dict) else {}

    def write_last_update(self, d: Dict) -> None:
        self._write_metadata("last_update", d)

    def read_integrity_log(self) -> Dict:
        val = self._read_metadata("data_integrity_log")
        return val if isinstance(val, dict) else {}

    def write_integrity_log(self, payload: Dict) -> None:
        self._write_metadata("data_integrity_log", payload)

    def _read_metadata(self, key: str):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM metadata WHERE key = %s", (key,))
                row = cur.fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def _write_metadata(self, key: str, value) -> None:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO metadata (key, value, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (key) DO UPDATE
                        SET value=EXCLUDED.value, updated_at=NOW()
                    """,
                    (key, json.dumps(value, default=str)),
                )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Stocks universe (replaces stocks_universe.csv)
    # ------------------------------------------------------------------ #

    def read_stocks_universe(self) -> Optional[pd.DataFrame]:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT ticker, name, exchange, active FROM stocks_universe")
                rows = cur.fetchall()
        finally:
            conn.close()
        if not rows:
            return None
        return pd.DataFrame([dict(r) for r in rows])

    def write_stocks_universe(self, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        rows = [
            (
                str(row.get("ticker", "")),
                str(row.get("name") or ""),
                str(row.get("exchange") or ""),
                bool(str(row.get("active", "true")).lower() in {"true", "1", "yes"}),
            )
            for _, row in df.iterrows()
            if str(row.get("ticker", ""))
        ]
        if not rows:
            return
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO stocks_universe (ticker, name, exchange, active)
                    VALUES %s
                    ON CONFLICT (ticker) DO UPDATE
                        SET name=EXCLUDED.name, exchange=EXCLUDED.exchange, active=EXCLUDED.active
                    """,
                    rows,
                )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Stubs matching LocalStore interface (no-ops in Postgres context)
    # ------------------------------------------------------------------ #

    def snapshot_ohlcv_backup(self, today=None):
        """No-op: Postgres has its own durability; no CSV backups needed."""
        return None

    def prune_ohlcv_backups(self, keep: int) -> int:
        return 0

    def write_mcap_snapshot(self, date, df: pd.DataFrame) -> None:
        """Store daily mcap snapshot in metadata table."""
        if df is None or df.empty:
            return
        if isinstance(date, _dt.datetime):
            iso = date.date().isoformat()
        elif isinstance(date, _dt.date):
            iso = date.isoformat()
        else:
            iso = pd.to_datetime(str(date)).date().isoformat()
        self._write_metadata(f"mcap_daily_{iso}", df.to_dict(orient="records"))

    def list_mcap_snapshots(self) -> List[str]:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key FROM metadata WHERE key LIKE 'mcap_daily_%' ORDER BY key"
                )
                return [r[0].replace("mcap_daily_", "") for r in cur.fetchall()]
        finally:
            conn.close()


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # NaN → None
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None
