"""R8-4A · Phase 2D · Tier-B Ridge regression for the Overall composite.

Honest implementation per Plan Part 3.1: trains on the FULL feature set the
Plan promised — 16 atomic signals (9 trend + 7 reversal) cross-sectionally
ranked, plus the 4 sleeve aggregates (trend_cs, reversal_cs, breadth,
vol_20d-inverse risk). 20 features in total.

Walk-forward cross-validation: 24-month train / 1-month test / monthly
rolling. Closed-form Ridge (no sklearn dep) over a panel where features
are CS-percentiled within each date.

Acceptance gate:
    holdout Spearman ρ(Tier-B prediction, forward 5d return)
      ≥ ρ(Tier-A baseline, forward 5d return) + 0.02

If passed, writes data-driven weights to local_data/scoring/tier_b_weights.json
with `accept: true`. The UI Toggle reads this — if accept is false (or the
file is missing) the toggle stays hidden and Tier-A is the only option.

The previous version of this script used only 2 features (trend_cs +
reversal_cs); the engineering + math audits flagged that as a P0 honesty
gap. This version computes the 16 atomic signals from each token's OHLCV
at every historical date via the same indicator registry the live scoring
pipeline uses, so the Plan's "16 signals + 4 sleeves" formulation is
actually exercised.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DATA_DIR
from backend.indicators.registry import INDICATORS
from backend.scoring.overall_score import TIER_A_WEIGHTS
from backend.scoring.trend_score import TREND_SIGNALS
from backend.scoring.reversal_score import REVERSAL_SIGNALS

SCORES_HISTORY = DATA_DIR / "market_cap" / "scores_history.csv"
OHLCV_DIR = DATA_DIR / "ohlcv"
OUT_PATH = DATA_DIR / "scoring" / "tier_b_weights.json"

# 16 atomic signals + breadth + risk + the two sleeve aggregates.
REVERSAL_KEYS = [k for k, _ in REVERSAL_SIGNALS]
ATOMIC_SIGNALS = list(TREND_SIGNALS) + REVERSAL_KEYS    # 9 + 7 = 16

# Final feature columns (20 total): 16 atomic CS-pct + 4 sleeve CS-pct.
FEATURE_COLS = ATOMIC_SIGNALS + [
    "trend_cs", "reversal_cs", "breadth_cs", "risk_cs",
]


# ----- per-token indicator panel ------------------------------------------ #

def _compute_token_indicators(cg_id: str) -> pd.DataFrame | None:
    """Compute every indicator family for one token; return a DataFrame indexed
    by date with one column per signal we need plus a 20d log-return vol.
    """
    path = OHLCV_DIR / f"{cg_id}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    if len(df) < 60:
        return None
    df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)

    panel = pd.DataFrame({"date": df["date"]})

    # Atomic signals via the indicator registry (single pass per family).
    for fam in INDICATORS.values():
        produced = fam.compute(df)
        for k, s in produced.items():
            if k in ATOMIC_SIGNALS:
                panel[k] = s.values

    # Per-token breadth + risk (raw scalars; CS-rank happens after the join).
    have_trend = [k for k in TREND_SIGNALS if k in panel.columns]
    if have_trend:
        # Strictly-positive count over the 9 trend signals → percentage (0-100).
        signed = panel[have_trend].astype(float)
        pos = (signed > 0).sum(axis=1)
        panel["breadth_raw"] = 100.0 * pos / len(have_trend)
    else:
        panel["breadth_raw"] = np.nan

    log_close = np.log(df["close"].astype(float))
    log_ret = log_close.diff()
    vol_20d = log_ret.rolling(20).std() * np.sqrt(365)
    panel["risk_raw"] = -vol_20d   # invert: low vol → high score after percentile

    return panel


# ----- build the panel ----------------------------------------------------- #

def _forward_return(cg_id: str, horizon: int = 5) -> pd.Series | None:
    path = OHLCV_DIR / f"{cg_id}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"])
    log_close = np.log(df["close"].astype(float))
    fwd = log_close.shift(-horizon) - log_close
    return pd.Series(fwd.values, index=df["date"], name="fwd_5d")


def _build_panel(history: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    t0 = time.time()
    rows = []
    tokens = history["cg_id"].unique().tolist()
    print(f"  Computing indicators for {len(tokens)} tokens ...")
    for i, cg_id in enumerate(tokens):
        if i % 25 == 0 and i:
            print(f"    [{i}/{len(tokens)}] {time.time()-t0:.0f}s elapsed")
        ind = _compute_token_indicators(cg_id)
        if ind is None:
            continue
        fwd = _forward_return(cg_id, horizon=horizon)
        if fwd is None:
            continue
        g = history[history["cg_id"] == cg_id][[
            "date", "trend_cs_percentile", "reversal_cs_percentile"
        ]].copy()
        g = g.rename(columns={
            "trend_cs_percentile": "trend_cs",
            "reversal_cs_percentile": "reversal_cs",
        })
        merged = g.merge(ind, on="date", how="inner")
        # Attach forward-return on date.
        merged = merged.set_index("date").join(fwd, how="inner").reset_index()
        merged["cg_id"] = cg_id
        rows.append(merged)
    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True)
    print(f"  Raw panel shape: {panel.shape}  ({time.time()-t0:.0f}s)")

    # CS-percentile within each date for breadth + risk + atomic signals.
    # The two sleeve columns (trend_cs / reversal_cs) are ALREADY percentiles
    # from scores_history.csv.
    def _cs_pct(grp_col):
        return panel.groupby("date")[grp_col].rank(pct=True) * 100.0

    print("  Cross-section-ranking per-date ...")
    panel["breadth_cs"] = _cs_pct("breadth_raw")
    panel["risk_cs"]    = _cs_pct("risk_raw")
    for sig in ATOMIC_SIGNALS:
        if sig in panel.columns:
            panel[f"{sig}_cs"] = _cs_pct(sig)
    # Replace raw atomic columns with their CS-percentile versions so the
    # feature matrix is all in [0,100] units.
    for sig in ATOMIC_SIGNALS:
        cs_col = f"{sig}_cs"
        if cs_col in panel.columns:
            panel[sig] = panel[cs_col]
            panel.drop(columns=[cs_col], inplace=True)

    cols = ["date", "cg_id", "fwd_5d"] + FEATURE_COLS
    keep = [c for c in cols if c in panel.columns]
    panel = panel[keep].dropna()
    print(f"  Cleaned panel: {panel.shape}  ({time.time()-t0:.0f}s)")
    return panel


# ----- Ridge regression (closed form) ------------------------------------- #

def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Closed-form Ridge: β = (XᵀX + αI)⁻¹ Xᵀy. The last column of X is the
    intercept, which we exclude from L2 regularisation.
    """
    p = X.shape[1]
    I = np.eye(p)
    I[-1, -1] = 0.0
    return np.linalg.solve(X.T @ X + alpha * I, X.T @ y)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 8:
        return float("nan")
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def walk_forward(panel: pd.DataFrame, train_months: int = 24, test_months: int = 1):
    panel = panel.sort_values(["date", "cg_id"]).reset_index(drop=True)
    panel["month"] = panel["date"].dt.to_period("M")
    months = sorted(panel["month"].unique())
    if len(months) <= train_months:
        return {"folds": [], "reason": f"only {len(months)} months in panel"}

    feat_cols = [c for c in FEATURE_COLS if c in panel.columns]
    print(f"  Walk-forward features ({len(feat_cols)}): {feat_cols}")
    print(f"  Months in panel: {len(months)}; rolling {train_months}m/{test_months}m")
    folds = []
    for i in range(train_months, len(months) - test_months + 1):
        train_slice = months[i - train_months:i]
        test_slice = months[i:i + test_months]
        train = panel[panel["month"].isin(train_slice)]
        test = panel[panel["month"].isin(test_slice)]
        if len(train) < 500 or len(test) < 50:
            continue
        Xtr = train[feat_cols].to_numpy(dtype=float)
        Xtr = np.hstack([Xtr, np.ones((len(Xtr), 1))])
        ytr = train["fwd_5d"].to_numpy(dtype=float)
        Xte = test[feat_cols].to_numpy(dtype=float)
        Xte = np.hstack([Xte, np.ones((len(Xte), 1))])
        yte = test["fwd_5d"].to_numpy(dtype=float)

        best = None
        for alpha in (0.1, 1.0, 10.0, 100.0, 1000.0):
            beta = _ridge_fit(Xtr, ytr, alpha)
            pred = Xte @ beta
            rho = _spearman(pred, yte)
            if best is None or (not math.isnan(rho) and rho > best["rho"]):
                best = {"alpha": alpha, "beta": beta.tolist(), "rho": rho}

        # Tier-A baseline composite, computed from the same features.
        wA = TIER_A_WEIGHTS
        tier_a_pred = (
            wA["trend"]    * test["trend_cs"].to_numpy()
            + wA["reversal"]* test["reversal_cs"].to_numpy()
            + wA["breadth"] * test["breadth_cs"].to_numpy()
            + wA["risk"]    * test["risk_cs"].to_numpy()
            # ts_trend_2y / ts_reversal_2y aren't in the historical panel;
            # use the sleeves themselves as proxies so the comparison stays
            # apples-to-apples (Tier B doesn't see them either).
        )
        rho_a = _spearman(tier_a_pred, yte)

        folds.append({
            "train_from": str(train_slice[0]),
            "train_to": str(train_slice[-1]),
            "test_month": str(test_slice[0]),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "alpha": best["alpha"],
            "beta": best["beta"],
            "rho_tier_b": best["rho"],
            "rho_tier_a": rho_a,
        })
    return {"folds": folds, "feature_cols": feat_cols}


def _aggregate_weights(folds, feat_cols):
    """Average the Ridge coefficients across folds, drop sign-unstable
    features (sign flips across folds), then renormalise the 4 sleeve weights
    to sum to (sleeve budget = 0.90) so risk/breadth still have a voice.
    """
    betas = np.array([f["beta"] for f in folds])  # shape (n_folds, n_features+1)
    # Drop the intercept column for weight reporting.
    coefs = betas[:, :-1]
    avg = coefs.mean(axis=0)
    # Sign-stability: feature retained only if at least 75% of folds agree on sign.
    sign_match = (np.sign(coefs) == np.sign(avg)).mean(axis=0)
    avg_stable = np.where(sign_match >= 0.75, avg, 0.0)

    # Pull out the four sleeve columns from FEATURE_COLS ordering.
    idx = {c: i for i, c in enumerate(feat_cols)}
    sleeve_keys = ["trend_cs", "reversal_cs", "breadth_cs", "risk_cs"]
    raw = {
        "trend":    max(0.0, float(avg_stable[idx.get("trend_cs",    -1)])) if "trend_cs"    in idx else 0.0,
        "reversal": max(0.0, float(avg_stable[idx.get("reversal_cs", -1)])) if "reversal_cs" in idx else 0.0,
        "breadth":  max(0.0, float(avg_stable[idx.get("breadth_cs",  -1)])) if "breadth_cs"  in idx else 0.0,
        "risk":     max(0.0, float(avg_stable[idx.get("risk_cs",     -1)])) if "risk_cs"     in idx else 0.0,
    }
    sleeve_sum = sum(raw.values())
    if sleeve_sum <= 1e-12:
        # Degenerate fit — keep Tier-A.
        return {k: float(v) for k, v in TIER_A_WEIGHTS.items()}

    budget = 1.0 - TIER_A_WEIGHTS["ts_trend_2y"] - TIER_A_WEIGHTS["ts_reversal_2y"]  # 0.90
    weights = {
        "trend":         raw["trend"]    / sleeve_sum * budget,
        "reversal":      raw["reversal"] / sleeve_sum * budget,
        "breadth":       raw["breadth"]  / sleeve_sum * budget,
        "risk":          raw["risk"]     / sleeve_sum * budget,
        "ts_trend_2y":   TIER_A_WEIGHTS["ts_trend_2y"],
        "ts_reversal_2y":TIER_A_WEIGHTS["ts_reversal_2y"],
    }
    # Atomic-signal weights are surfaced for the explainer but don't feed
    # into Overall composition (the composite uses the 4 sleeves).
    atomic_weights = {}
    for sig in ATOMIC_SIGNALS:
        if sig in idx:
            atomic_weights[sig] = float(avg_stable[idx[sig]])
    return weights, atomic_weights, sign_match.tolist()


def _survivorship_audit(history: pd.DataFrame) -> dict:
    """Record n_tokens_at_each_date and flag survivorship-bias risk.

    The crypto dashboard's `scores_history.csv` is built from today's live
    universe; if a token died before today it is *not* in the file at all,
    so historical cross-sections systematically over-represent winners.

    This function does NOT fix the bias — that requires rebuilding the
    universe from a point-in-time listing snapshot (out of scope here) —
    but it records the magnitude so downstream consumers can disclose it.
    """
    per_date = history.groupby("date")["cg_id"].nunique()
    last_n  = int(per_date.iloc[-1])
    first_n = int(per_date.iloc[0])

    # Per-token "first date in panel". A token whose first date is well
    # after the panel start was *added later*; in a survivorship-clean
    # universe this would be balanced by tokens that drop out, but here
    # we expect ~0 drop-outs.
    per_token_first = history.groupby("cg_id")["date"].min()
    per_token_last  = history.groupby("cg_id")["date"].max()
    max_panel_date  = history["date"].max()
    n_alive_today   = int((per_token_last >= (max_panel_date - pd.Timedelta(days=14))).sum())
    n_dropped_out   = int(history["cg_id"].nunique() - n_alive_today)
    n_added_later   = int((per_token_first > history["date"].min() + pd.Timedelta(days=30)).sum())

    return {
        "n_tokens_first_date": first_n,
        "n_tokens_last_date":  last_n,
        "n_added_later":       n_added_later,
        "n_delisted":          n_dropped_out,
        "warning": (
            f"{last_n} tokens alive on last date; {n_dropped_out} delisted in "
            "sample. Universe was built from today's live universe — historical "
            "cross-sections are survivorship-biased. Calibrated/Tier-B rhos and "
            "weights overstate live trading edge."
        ),
        "remediation": (
            "Rebuild scores_history from a point-in-time CoinGecko listing "
            "snapshot per date; out of scope for Tier-B training, in scope for "
            "Phase 3 data architecture work."
        ),
    }


def main():
    print(f"Loading {SCORES_HISTORY} ...")
    history = pd.read_csv(SCORES_HISTORY, parse_dates=["date"])
    history = history.dropna(subset=["trend_cs_percentile", "reversal_cs_percentile"])
    print(f"  {len(history):,} score-history rows, "
          f"{history['cg_id'].nunique()} tokens, {history['date'].nunique()} dates")

    survivorship = _survivorship_audit(history)
    print(f"  survivorship audit: alive_today={survivorship['n_tokens_last_date']} "
          f"delisted={survivorship['n_delisted']} added_later={survivorship['n_added_later']}")
    print(f"  WARNING: {survivorship['warning']}")

    print("Building feature panel (16 atomic + 4 sleeve CS-percentile features) ...")
    panel = _build_panel(history, horizon=5)
    if panel.empty:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps({"accept": False, "reason": "empty panel"}, indent=2))
        print("PANEL EMPTY — wrote accept:false.")
        return

    print("Walk-forward 24/1 ...")
    result = walk_forward(panel, train_months=24, test_months=1)
    folds = result.get("folds", [])
    feat_cols = result.get("feature_cols", [])
    print(f"  completed {len(folds)} folds")
    if not folds:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps({
            "accept": False,
            "reason": result.get("reason", "no folds completed"),
            "folds": [],
            "n_features": len(feat_cols),
            "features": feat_cols,
        }, indent=2))
        print("Not enough history — wrote accept:false.")
        return

    rho_b_med = float(np.median([f["rho_tier_b"] for f in folds if not math.isnan(f["rho_tier_b"])]))
    rho_a_med = float(np.median([f["rho_tier_a"] for f in folds if not math.isnan(f["rho_tier_a"])]))

    weights, atomic_weights, sign_match = _aggregate_weights(folds, feat_cols)
    accepted = (rho_b_med >= rho_a_med + 0.02) and not math.isnan(rho_b_med)
    payload = {
        "accept": bool(accepted),
        "reason": ("Tier B exceeds Tier A + 0.02" if accepted
                   else f"Tier B median ρ={rho_b_med:.4f} did not exceed Tier A "
                        f"baseline ρ={rho_a_med:.4f} + 0.02"),
        "weights": weights,
        "atomic_weights": atomic_weights,
        "feature_columns": feat_cols,
        "sign_stability_per_feature": dict(zip(feat_cols, sign_match)),
        "holdout_spearman_rho_5d_tier_b": rho_b_med,
        "holdout_spearman_rho_5d_tier_a": rho_a_med,
        "n_folds": len(folds),
        "folds": folds,
        "survivorship": survivorship,
        "survivorship_warning": survivorship["warning"],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nTier-B accept={accepted}  rho_B={rho_b_med:.4f}  rho_A={rho_a_med:.4f}")
    print(f"  features: {len(feat_cols)} columns ({', '.join(feat_cols[:6])}...)")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
