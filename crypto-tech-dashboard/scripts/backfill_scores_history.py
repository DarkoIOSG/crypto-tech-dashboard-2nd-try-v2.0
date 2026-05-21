"""
backfill_scores_history.py — P0-G fix (Option A).

Reconstructs the full per-day cross-sectional trend / reversal score
history from each token's persisted OHLCV CSV, and writes it to
local_data/market_cap/scores_history.csv.

Why this exists:
    Before this script, scores_history.csv only contained "today" because
    _append_scores_history_snapshot wrote a single row per cg_id per
    fetcher run. data_service.score_for() therefore reported 100.0 for
    every long-history token's 2y / 3y percentile (a 1-element percentile
    is always 100.0). Backfilling makes that read-out meaningful from day 1.

Algorithm:
    1. For every cg_id in ohlcv/, compute its full indicator series.
    2. Collect the union of all dates present (sorted asc).
    3. For each date d:
         a. Build snapshot dict: {cg_id: {sig: ind_series[sig].loc[d_idx]}}
            for tokens that have a row at d AND >=30 prior bars.
         b. Run cross_sectional_trend_scores + cross_sectional_reversal_scores
            on the snapshot.
         c. Cross-sectional percentile of those two score dicts.
         d. Emit one row per (date, cg_id).
    4. Atomic-write the whole frame to scores_history.csv.

Run it via the project venv:
    PYTHONPATH=. ./venv/bin/python scripts/backfill_scores_history.py

This module has NO try/except — it relies on store / scoring / indicators
to honour their own contracts (which they already do — Round-1 hardening).
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd

# Allow `python scripts/backfill_scores_history.py` from project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import PROJECT_ROOT  # noqa: E402
from backend.data.local_store import LocalStore  # noqa: E402
from backend.indicators.registry import INDICATORS  # noqa: E402
from backend.scoring.ranking import cross_sectional_percentile  # noqa: E402
from backend.scoring.reversal_score import cross_sectional_reversal_scores  # noqa: E402
from backend.scoring.trend_score import cross_sectional_trend_scores  # noqa: E402


log = logging.getLogger("backfill_scores_history")
MIN_HISTORY_FOR_SCORING = 30  # bars; matches data_service threshold


def _compute_indicators_for_token(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Run every registered family and flatten into a {signal_key: series}."""
    out: Dict[str, pd.Series] = {}
    for fam in INDICATORS.values():
        produced = fam.compute(df)
        for k, s in produced.items():
            out[k] = s
    return out


def _snapshot_dict_for_date(
    per_token_indicators: Dict[str, Dict[str, pd.Series]],
    per_token_date_idx: Dict[str, Dict[pd.Timestamp, int]],
    date: pd.Timestamp,
) -> Dict[str, Dict[str, float]]:
    """Build {cg_id: {signal: float}} for one calendar date.

    Tokens without that date OR with fewer than MIN_HISTORY_FOR_SCORING
    rows up to that date are skipped (their signals would be ~zero anyway).
    """
    snapshot: Dict[str, Dict[str, float]] = {}
    for cg_id, ind in per_token_indicators.items():
        idx_map = per_token_date_idx.get(cg_id, {})
        row_idx = idx_map.get(date)
        if row_idx is None or row_idx < MIN_HISTORY_FOR_SCORING:
            continue
        signals: Dict[str, float] = {}
        for k, s in ind.items():
            if row_idx >= len(s):
                continue
            v = s.iloc[row_idx]
            if v is None:
                continue
            fv = float(v)
            if fv == fv:  # not NaN
                signals[k] = fv
        if signals:
            snapshot[cg_id] = signals
    return snapshot


def backfill(data_dir: Path) -> int:
    """Run the full backfill. Returns the number of rows written."""
    store = LocalStore(data_dir)
    cg_ids = store.list_ohlcv_ids()
    log.info("backfill: %d cg_ids found in ohlcv/", len(cg_ids))

    # Step 1: load OHLCV + compute indicators per token.
    per_token_ind: Dict[str, Dict[str, pd.Series]] = {}
    per_token_date_idx: Dict[str, Dict[pd.Timestamp, int]] = {}
    all_dates: set = set()

    t0 = time.time()
    for n, cg_id in enumerate(cg_ids, start=1):
        df = store.read_ohlcv(cg_id)
        if df is None or len(df) < MIN_HISTORY_FOR_SCORING:
            log.debug("skip %s: not enough rows", cg_id)
            continue
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        ind = _compute_indicators_for_token(df)
        if not ind:
            continue
        per_token_ind[cg_id] = ind
        # row_idx for each calendar date in this token.
        idx_map: Dict[pd.Timestamp, int] = {}
        for i, d in enumerate(df["date"]):
            idx_map[d] = i
            all_dates.add(d)
        per_token_date_idx[cg_id] = idx_map
        if n % 25 == 0:
            log.info("  loaded indicators for %d / %d tokens", n, len(cg_ids))
    log.info(
        "loaded indicators for %d tokens in %.1fs",
        len(per_token_ind),
        time.time() - t0,
    )
    if not all_dates:
        log.error("no dates found; aborting")
        return 0

    sorted_dates: List[pd.Timestamp] = sorted(all_dates)
    log.info(
        "covering %d distinct dates (%s .. %s)",
        len(sorted_dates),
        sorted_dates[0].date(),
        sorted_dates[-1].date(),
    )

    # Step 2: per-date cross-sectional scoring.
    out_rows: List[Dict] = []
    t1 = time.time()
    for di, date in enumerate(sorted_dates, start=1):
        snapshot = _snapshot_dict_for_date(per_token_ind, per_token_date_idx, date)
        if not snapshot:
            continue
        trend = cross_sectional_trend_scores(snapshot)
        reversal = cross_sectional_reversal_scores(snapshot)
        cs_trend = cross_sectional_percentile(trend)
        cs_rev = cross_sectional_percentile(reversal)
        iso = date.date().isoformat()
        for cg_id in snapshot:
            out_rows.append(
                {
                    "date": iso,
                    "cg_id": cg_id,
                    "trend_score": float(trend.get(cg_id, 0.0)),
                    "reversal_score": float(reversal.get(cg_id, 0.0)),
                    "trend_cs_percentile": float(cs_trend.get(cg_id, 0.0)),
                    "reversal_cs_percentile": float(cs_rev.get(cg_id, 0.0)),
                }
            )
        if di % 200 == 0:
            log.info(
                "  scored %d / %d dates  (rows so far: %d)",
                di,
                len(sorted_dates),
                len(out_rows),
            )
    log.info(
        "per-date scoring done in %.1fs; %d total rows",
        time.time() - t1,
        len(out_rows),
    )

    # Step 3: atomic write of the full file.
    df_out = pd.DataFrame(
        out_rows,
        columns=[
            "date",
            "cg_id",
            "trend_score",
            "reversal_score",
            "trend_cs_percentile",
            "reversal_cs_percentile",
        ],
    )
    df_out = df_out.sort_values(["date", "cg_id"]).reset_index(drop=True)
    target = store._scores_history_path  # noqa: SLF001
    store._atomic_write_csv(df_out, target)  # noqa: SLF001
    log.info("wrote %d rows to %s", len(df_out), target)
    return len(df_out)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    data_dir = Path(PROJECT_ROOT) / "local_data"
    n = backfill(data_dir)
    print(f"backfill done: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
