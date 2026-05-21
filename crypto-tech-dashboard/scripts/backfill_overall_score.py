"""R8-2A · Plan acceptance: scores_history.csv must carry overall_score
and overall_cs_percentile columns. Older rows from before this column
existed get backfilled here from the historical trend + reversal CS
percentiles plus per-token breadth + risk computed from OHLCV at each date.

This is a one-shot rebuild — it does not replace the daily snapshot path
(that one will write the new columns going forward via the fetcher
patch in this commit).

Strategy:
  1. Load existing scores_history.csv.
  2. For each (date, cg_id), compute the 4 sleeves needed by Tier-A:
     - trend / reversal: already in the row as CS percentiles
     - breadth: from the 9 trend signals at that date, then CS-rank per date
     - risk: from -vol_20d at that date, then CS-rank per date
  3. compute_overall_score per row.
  4. CS-rank overall per date.
  5. Atomic write the augmented CSV.

TS-2y sleeves remain None historically (snapshot only retains scores,
not the rolling history); compute_overall_score maps None → 50 (neutral)
so the backfill is conservative.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DATA_DIR
from backend.indicators.registry import INDICATORS
from backend.scoring.overall_score import (
    TIER_A_WEIGHTS,
    compute_overall_score,
)
from backend.scoring.ranking import cross_sectional_percentile
from backend.scoring.trend_score import TREND_SIGNALS

SCORES_HISTORY = DATA_DIR / "market_cap" / "scores_history.csv"
OHLCV_DIR = DATA_DIR / "ohlcv"


def _trend_signal_panel(cg_id: str) -> pd.DataFrame | None:
    """Return per-date {date, signal1, ..., signal9, vol_20d} DataFrame."""
    path = OHLCV_DIR / f"{cg_id}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    if len(df) < 60:
        return None
    df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
    out = pd.DataFrame({"date": df["date"]})
    for fam in INDICATORS.values():
        produced = fam.compute(df)
        for k, s in produced.items():
            if k in TREND_SIGNALS or k == "vol_20d":
                out[k] = s.values
    return out


def main():
    print(f"Loading {SCORES_HISTORY} ...")
    if not SCORES_HISTORY.exists():
        print("scores_history.csv missing — abort.")
        return
    hist = pd.read_csv(SCORES_HISTORY, parse_dates=["date"])
    print(f"  {len(hist):,} rows, {hist['cg_id'].nunique()} tokens, {hist['date'].nunique()} dates")
    if "overall_score" in hist.columns and hist["overall_score"].notna().all():
        print("  Already populated — nothing to do.")
        return

    print("Building per-token signal panels ...")
    t0 = time.time()
    panels = {}
    tokens = hist["cg_id"].unique().tolist()
    for i, cg_id in enumerate(tokens):
        if i % 25 == 0 and i:
            print(f"  [{i}/{len(tokens)}] {time.time()-t0:.0f}s elapsed")
        p = _trend_signal_panel(cg_id)
        if p is not None:
            panels[cg_id] = p

    print("Joining signals into scores_history rows ...")
    pieces = []
    for cg_id, panel in panels.items():
        rows = hist[hist["cg_id"] == cg_id]
        merged = rows.merge(panel, on="date", how="left")
        pieces.append(merged)
    augmented = pd.concat(pieces, ignore_index=True) if pieces else hist.copy()
    print(f"  augmented panel: {augmented.shape}")

    print("Computing breadth + risk + overall per (date, token) ...")
    have_trend = [s for s in TREND_SIGNALS if s in augmented.columns]

    # breadth = % of 9 trend signals strictly positive
    if have_trend:
        signed = augmented[have_trend].astype(float)
        pos = (signed > 0).sum(axis=1)
        augmented["breadth_raw"] = 100.0 * pos / len(have_trend)
    else:
        augmented["breadth_raw"] = np.nan

    # risk = -vol_20d (inverted so low vol -> high CS rank)
    augmented["risk_raw"] = -augmented.get("vol_20d", np.nan)

    # CS-rank within each date.
    def _cs_pct(grp_col):
        return augmented.groupby("date")[grp_col].rank(pct=True) * 100.0

    augmented["breadth_cs"] = _cs_pct("breadth_raw")
    augmented["risk_cs"] = _cs_pct("risk_raw")

    # compute_overall_score is scalar; vectorise via apply.
    def _overall(row):
        return compute_overall_score(
            trend_cs_pct=row["trend_cs_percentile"],
            reversal_cs_pct=row["reversal_cs_percentile"],
            breadth_cs_pct=row.get("breadth_cs", 50.0),
            risk_cs_pct=row.get("risk_cs", 50.0),
            ts_trend_2y_pct=None,
            ts_reversal_2y_pct=None,
        )

    augmented["overall_score"] = augmented.apply(_overall, axis=1)
    augmented["overall_cs_percentile"] = (
        augmented.groupby("date")["overall_score"].rank(pct=True) * 100.0
    )

    # Trim to the schema.
    out_cols = [
        "date", "cg_id",
        "trend_score", "reversal_score",
        "trend_cs_percentile", "reversal_cs_percentile",
        "overall_score", "overall_cs_percentile",
    ]
    final = augmented[out_cols].copy()
    final = final.sort_values(["date", "cg_id"]).reset_index(drop=True)
    print(f"  final shape: {final.shape}, overall_score non-null: {final['overall_score'].notna().sum():,}")

    tmp = SCORES_HISTORY.with_suffix(".csv.tmp")
    final.to_csv(tmp, index=False)
    tmp.replace(SCORES_HISTORY)
    print(f"Wrote {SCORES_HISTORY}  ({time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main()
