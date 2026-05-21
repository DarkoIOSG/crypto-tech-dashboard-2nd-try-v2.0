"""Pure-function data validators for OHLCV and Top-200 dataframes.

Per PLAN A2b: vectorized pandas checks only, no try/except, no row loops.
Each validator returns a list of issue strings (empty list == OK).
Schema matches `local_store.OHLCV_COLUMNS` and `coingecko_client.fetch_top_n_markets`.
"""

from __future__ import annotations

import datetime as _dt
from typing import List

import pandas as pd


# Canonical schemas (mirrored from sibling modules — do not re-import to keep
# this module side-effect-free and importable without the wider package).
OHLCV_EXPECTED_COLUMNS: List[str] = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
]
TOP200_REQUIRED_COLUMNS: List[str] = [
    # R8-1C: Phase-2 item 5 demands market_cap_rank / fdv / total_volume /
    # supply / 24h pct for the Market Info panel. Validator enforces the
    # full 12-column schema so a regression to the old 5-col write would
    # surface in the integrity log instead of silently breaking the UI.
    "id",
    "symbol",
    "name",
    "current_price",
    "market_cap",
    "market_cap_rank",
    "fully_diluted_valuation",
    "total_volume",
    "circulating_supply",
    "total_supply",
    "max_supply",
    "price_change_percentage_24h",
]

_OHLC_COLS: List[str] = ["open", "high", "low", "close"]
_RECENCY_DAYS: int = 7
_MAX_GAP_DAYS: int = 7
_TOP200_MIN_ROWS: int = 50
_TOP200_MAX_ROWS: int = 500


def validate_ohlcv(df: pd.DataFrame) -> List[str]:
    """Validate an OHLCV dataframe. Returns list of issue strings (empty == OK)."""
    issues: List[str] = []

    # 1. Column presence.
    missing_cols = [c for c in OHLCV_EXPECTED_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(f"missing columns: {missing_cols}")
        # Without the required columns, downstream checks would be meaningless.
        return issues

    # Empty frame is itself an issue worth flagging.
    if df.empty:
        issues.append("empty dataframe")
        return issues

    # 2. Date parseability + monotonicity + duplicates.
    parsed_dates = pd.to_datetime(df["date"], errors="coerce")
    n_unparseable = int(parsed_dates.isna().sum())
    if n_unparseable > 0:
        issues.append(f"unparseable dates: {n_unparseable}")

    # Drop NaT rows for the remaining date-based checks (they were already flagged).
    valid_mask = parsed_dates.notna()
    valid_dates = parsed_dates[valid_mask]

    n_dupes = int(valid_dates.duplicated().sum())
    if n_dupes > 0:
        issues.append(f"duplicate dates: {n_dupes}")

    if not valid_dates.is_monotonic_increasing:
        issues.append("dates not strictly monotonic increasing")

    # 3. Numeric range checks.
    # OHLC: strictly > 0 and no NaN.
    ohlc = df[_OHLC_COLS].apply(pd.to_numeric, errors="coerce")
    ohlc_nan_counts = ohlc.isna().sum()
    ohlc_nan_total = int(ohlc_nan_counts.sum())
    if ohlc_nan_total > 0:
        offenders = ohlc_nan_counts[ohlc_nan_counts > 0].to_dict()
        issues.append(f"NaN in OHLC: {offenders}")

    nonpositive_ohlc = (ohlc <= 0).sum()
    nonpositive_total = int(nonpositive_ohlc.sum())
    if nonpositive_total > 0:
        offenders = nonpositive_ohlc[nonpositive_ohlc > 0].to_dict()
        issues.append(f"non-positive OHLC: {offenders}")

    # Volume: >= 0 (can be 0). NaN volume is also flagged.
    volume = pd.to_numeric(df["volume"], errors="coerce")
    n_vol_nan = int(volume.isna().sum())
    if n_vol_nan > 0:
        issues.append(f"NaN volume rows: {n_vol_nan}")
    n_vol_neg = int((volume < 0).sum())
    if n_vol_neg > 0:
        issues.append(f"negative volume rows: {n_vol_neg}")

    # 4. low <= open <= high  AND  low <= close <= high (vectorized).
    low = ohlc["low"]
    high = ohlc["high"]
    open_ = ohlc["open"]
    close = ohlc["close"]

    bad_open = ((open_ < low) | (open_ > high)).fillna(False)
    bad_close = ((close < low) | (close > high)).fillna(False)
    bad_lh = (low > high).fillna(False)

    n_bad_open = int(bad_open.sum())
    n_bad_close = int(bad_close.sum())
    n_bad_lh = int(bad_lh.sum())
    if n_bad_open > 0:
        issues.append(f"open outside [low, high]: {n_bad_open} rows")
    if n_bad_close > 0:
        issues.append(f"close outside [low, high]: {n_bad_close} rows")
    if n_bad_lh > 0:
        issues.append(f"low > high: {n_bad_lh} rows")

    # 5. Gap check: no gap > 7 days between consecutive (sorted) dates.
    if len(valid_dates) >= 2:
        sorted_dates = valid_dates.sort_values().reset_index(drop=True)
        deltas = sorted_dates.diff().dt.days.dropna()
        big_gaps = deltas[deltas > _MAX_GAP_DAYS]
        n_big_gaps = int(big_gaps.shape[0])
        if n_big_gaps > 0:
            max_gap = int(big_gaps.max())
            issues.append(
                f"gap > {_MAX_GAP_DAYS} days: {n_big_gaps} gaps (max={max_gap} days)"
            )

    # 6. Recency check: last date within last 7 days of today (UTC).
    if len(valid_dates) >= 1:
        last_date = valid_dates.max()
        today_utc = pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).date())
        # Compare on calendar-date basis (strip tz/time on last_date).
        last_date_naive = pd.Timestamp(last_date).tz_localize(None).normalize()
        age_days = (today_utc - last_date_naive).days
        if age_days > _RECENCY_DAYS:
            issues.append(f"stale: last_date={last_date_naive.strftime('%Y-%m-%d')}")

    return issues


def validate_top200(df: pd.DataFrame) -> List[str]:
    """Validate a Top-200 (current snapshot) dataframe."""
    issues: List[str] = []

    missing_cols = [c for c in TOP200_REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(f"missing columns: {missing_cols}")
        return issues

    n_rows = int(df.shape[0])
    if n_rows < _TOP200_MIN_ROWS or n_rows > _TOP200_MAX_ROWS:
        issues.append(
            f"row count out of sanity range [{_TOP200_MIN_ROWS}, {_TOP200_MAX_ROWS}]: {n_rows}"
        )

    if n_rows == 0:
        return issues

    # id uniqueness + non-empty.
    ids = df["id"].astype("string")
    n_id_nan = int(ids.isna().sum())
    n_id_empty = int((ids.fillna("").str.strip() == "").sum())
    if n_id_empty > 0:
        issues.append(f"empty/NaN id rows: {n_id_empty}")
    n_id_dupes = int(ids.duplicated().sum())
    if n_id_dupes > 0:
        issues.append(f"duplicate id rows: {n_id_dupes}")
    # Avoid an unused-var lint by referencing n_id_nan inside the empty count above.
    _ = n_id_nan

    # current_price > 0.
    price = pd.to_numeric(df["current_price"], errors="coerce")
    n_price_bad = int(((price.isna()) | (price <= 0)).sum())
    if n_price_bad > 0:
        issues.append(f"current_price <= 0 or NaN: {n_price_bad}")

    # market_cap > 0.
    mcap = pd.to_numeric(df["market_cap"], errors="coerce")
    n_mcap_bad = int(((mcap.isna()) | (mcap <= 0)).sum())
    if n_mcap_bad > 0:
        issues.append(f"market_cap <= 0 or NaN: {n_mcap_bad}")

    return issues


def summarize_validation(issues: List[str]) -> str:
    """Return a one-line summary of an issue list."""
    if not issues:
        return "OK"
    n = len(issues)
    joined = "; ".join(issues)
    return f"{n} issues: {joined}"


class DataValidator:
    """P0-L: Operates on a `LocalStore` to run `validate_ohlcv` over every
    on-disk OHLCV file and `validate_top200` over the current universe,
    persisting the per-token issue list to
    `local_data/metadata/data_integrity_log.json` via the store's atomic
    JSON writer.

    The fetcher's `_maybe_run_validator()` calls `.run()` on the tail of
    `run_daily_update` / `run_full_initial_load`. Previously a stub in
    `main.py` returned None and the integrity log was never written.

    No try/except here — store atomicity is the only exception boundary
    and lives inside `local_store._atomic_write_json`.
    """

    def __init__(self, store):
        self.store = store

    def run(self) -> dict:
        cg_ids = self.store.list_ohlcv_ids()
        per_token: List[dict] = []
        n_ok = 0
        for cg_id in cg_ids:
            df = self.store.read_ohlcv(cg_id)
            # Empty/missing CSV: also surface as an issue rather than skip.
            if df is None:
                per_token.append({"cg_id": cg_id, "issues": ["missing or empty CSV"]})
                continue
            issues = validate_ohlcv(df)
            if issues:
                per_token.append({"cg_id": cg_id, "issues": issues})
            else:
                n_ok += 1

        # Top-200 universe snapshot — read directly via the store.
        top_issues: List[str] = []
        top_df = self.store.read_top200_current()
        if top_df is None or top_df.empty:
            top_issues = ["missing or empty top200_current.csv"]
        else:
            top_issues = validate_top200(top_df)

        now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        payload = {
            "last_run": now_iso,
            "tokens_checked": int(len(cg_ids)),
            "ohlcv_ok": int(n_ok),
            "ohlcv_with_issues": int(len(per_token)),
            "issues": per_token,
            "top200_issues": top_issues,
        }
        self.store.write_integrity_log(payload)
        return payload
