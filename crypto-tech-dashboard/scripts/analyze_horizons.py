"""Multi-horizon sleeve / signal calibration — v2 (Newey-West, chronological holdout,
cluster bootstrap, atomic re-weighting, sharpe).

Builds a single panel of (date, cg_id) x [16 atomic signals + 4 sleeve
percentiles + 4 forward-return horizons] from scores_history.csv + OHLCV.

v2 changes (responding to MIT peer-review):
 - `_fmb_rho` now returns Newey-West HAC standard error with lag = h-1 so that
   AR(h-1) in overlapping forward returns deflates the t-stat honestly.
 - chronological 80/20 train/holdout split (NOT random).
 - `evaluate_oos_weights(...)`: fits sleeve weights on train slice only,
   evaluates composite-vs-fwd_h Spearman rho on holdout slice. Fully
   reproducible.
 - cluster bootstrap on cg_id for sleeve rho (token-level dependence audit).
 - within-sleeve atomic re-weighting helper for the trend sleeve (responds
   to MIT critique #6: "drop trend" is dominated by re-weighting MA-cross atomics).
 - simulated long-short decile Sharpe / turnover.

Run:
    python3 scripts/analyze_horizons.py             # uses cached panel
    python3 scripts/analyze_horizons.py --force     # rebuilds the panel
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DATA_DIR
from backend.indicators.registry import INDICATORS
from backend.scoring.trend_score import TREND_SIGNALS
from backend.scoring.reversal_score import REVERSAL_SIGNALS

SCORES_HISTORY = DATA_DIR / "market_cap" / "scores_history.csv"
OHLCV_DIR = DATA_DIR / "ohlcv"
OUT_PATH = DATA_DIR / "scoring" / "horizon_calibration.json"
HOLDOUT_PATH = DATA_DIR / "scoring" / "holdout_walkforward.json"
PANEL_CACHE = DATA_DIR / "scoring" / "_horizon_panel_cache.pkl"

HORIZONS = [5, 10, 20, 60]
TRAIN_FRAC = 0.80                # chronological split

REVERSAL_KEYS = [k for k, _ in REVERSAL_SIGNALS]
ATOMIC_SIGNALS = list(TREND_SIGNALS) + REVERSAL_KEYS    # 16
SLEEVES = ["trend_cs", "reversal_cs", "breadth_cs", "risk_cs"]
FEATURE_COLS = ATOMIC_SIGNALS + SLEEVES                 # 20

# Atomic signals that compose each sleeve. Trend sleeve has 9 atomics; the
# MA-cross strength signals are the "babies" the MIT reviewer flagged.
TREND_ATOMICS = list(TREND_SIGNALS)                     # 9 signals
REVERSAL_ATOMICS = REVERSAL_KEYS                        # 7 signals

# Number of simultaneous tests in the multiple-comparison family:
# (20 features) x (4 horizons) = 80. Bonferroni alpha=0.05 -> |t| >= 3.16.
N_TESTS_FAMILY = len(FEATURE_COLS) * len(HORIZONS)
BONFERRONI_T = 3.16   # |t| critical for alpha=0.05 / 80 (z-approx)


# ----- panel construction (mirrors train_tier_b.py) ----------------------- #

def _compute_token_indicators(cg_id: str) -> pd.DataFrame | None:
    path = OHLCV_DIR / f"{cg_id}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    if len(df) < 90:
        return None
    df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)

    panel = pd.DataFrame({"date": df["date"]})
    for fam in INDICATORS.values():
        produced = fam.compute(df)
        for k, s in produced.items():
            if k in ATOMIC_SIGNALS:
                panel[k] = s.values

    have_trend = [k for k in TREND_SIGNALS if k in panel.columns]
    if have_trend:
        signed = panel[have_trend].astype(float)
        pos = (signed > 0).sum(axis=1)
        panel["breadth_raw"] = 100.0 * pos / len(have_trend)
    else:
        panel["breadth_raw"] = np.nan

    log_close = np.log(df["close"].astype(float))
    log_ret = log_close.diff()
    vol_20d = log_ret.rolling(20).std() * np.sqrt(365)
    panel["risk_raw"] = -vol_20d

    for h in HORIZONS:
        panel[f"fwd_{h}d"] = (log_close.shift(-h) - log_close).values
    return panel


def _build_panel(history: pd.DataFrame) -> pd.DataFrame:
    t0 = time.time()
    tokens = history["cg_id"].unique().tolist()
    print(f"  building indicator panel for {len(tokens)} tokens")
    rows: List[pd.DataFrame] = []
    for i, cg_id in enumerate(tokens):
        if i and i % 25 == 0:
            print(f"    [{i}/{len(tokens)}] {time.time()-t0:.0f}s")
        ind = _compute_token_indicators(cg_id)
        if ind is None:
            continue
        g = history[history["cg_id"] == cg_id][
            ["date", "trend_cs_percentile", "reversal_cs_percentile"]
        ].rename(columns={
            "trend_cs_percentile": "trend_cs",
            "reversal_cs_percentile": "reversal_cs",
        })
        merged = g.merge(ind, on="date", how="inner")
        merged["cg_id"] = cg_id
        rows.append(merged)
    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True)
    print(f"  raw panel rows={len(panel):,} ({time.time()-t0:.0f}s)")

    print("  cross-sectional ranking per date")
    panel["breadth_cs"] = panel.groupby("date")["breadth_raw"].rank(pct=True) * 100.0
    panel["risk_cs"]    = panel.groupby("date")["risk_raw"].rank(pct=True) * 100.0
    for sig in ATOMIC_SIGNALS:
        if sig in panel.columns:
            panel[f"{sig}_cs"] = panel.groupby("date")[sig].rank(pct=True) * 100.0
    for sig in ATOMIC_SIGNALS:
        cs_col = f"{sig}_cs"
        if cs_col in panel.columns:
            panel[sig] = panel[cs_col]
            panel.drop(columns=[cs_col], inplace=True)

    keep = ["date", "cg_id"] + FEATURE_COLS + [f"fwd_{h}d" for h in HORIZONS]
    panel = panel[[c for c in keep if c in panel.columns]]
    print(f"  done panel shape={panel.shape} ({time.time()-t0:.0f}s)")
    return panel


def _load_or_build_panel(history: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    if not force and PANEL_CACHE.exists():
        if PANEL_CACHE.stat().st_mtime >= SCORES_HISTORY.stat().st_mtime:
            print(f"  loading cached panel from {PANEL_CACHE.name}")
            return pd.read_pickle(PANEL_CACHE)
    panel = _build_panel(history)
    PANEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    try:
        panel.to_pickle(PANEL_CACHE)
        print(f"  cached panel to {PANEL_CACHE.name}")
    except Exception as e:
        print(f"  (could not cache panel: {e})")
    return panel


# ----- chronological split utility --------------------------------------- #

def _chronological_split(panel: pd.DataFrame, train_frac: float = TRAIN_FRAC
                         ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Split panel by date: first `train_frac` of unique dates -> train, rest -> holdout."""
    dates = np.sort(panel["date"].unique())
    cut_idx = int(len(dates) * train_frac)
    cutoff = pd.Timestamp(dates[cut_idx])
    train = panel[panel["date"] < cutoff].copy()
    holdout = panel[panel["date"] >= cutoff].copy()
    return train, holdout, cutoff


# ----- statistical primitives -------------------------------------------- #

def _per_date_spearman(panel: pd.DataFrame, feat: str, fwd: str) -> Tuple[np.ndarray, np.ndarray]:
    """Return (per_date_rho_array, per_date_obs_count_array) in date order."""
    rhos = []
    counts = []
    # iterate sorted by date to preserve time order (needed for NW)
    for d, grp in panel.sort_values("date").groupby("date", sort=True):
        m = grp[feat].notna() & grp[fwd].notna()
        n = int(m.sum())
        if n < 8:
            continue
        rx = grp.loc[m, feat].rank()
        ry = grp.loc[m, fwd].rank()
        if rx.std() == 0 or ry.std() == 0:
            continue
        rhos.append(float(np.corrcoef(rx, ry)[0, 1]))
        counts.append(n)
    return np.asarray(rhos, dtype=float), np.asarray(counts, dtype=int)


def _newey_west_se(x: np.ndarray, lag: int) -> float:
    """Newey-West HAC SE for the mean of x.

    Uses Bartlett kernel weights w_l = 1 - l/(lag+1).
    Returns sd_NW / sqrt(T) (i.e. SE of the mean).
    """
    x = np.asarray(x, dtype=float)
    T = len(x)
    if T < 5:
        return float("nan")
    mu = x.mean()
    u = x - mu
    gamma0 = float((u * u).sum() / T)
    lrv = gamma0
    L = max(0, int(lag))
    for l in range(1, L + 1):
        if l >= T:
            break
        w = 1.0 - l / (L + 1.0)
        cov = float((u[l:] * u[:-l]).sum() / T)
        lrv += 2.0 * w * cov
    if lrv <= 0:
        # Fall back to OLS SE if NW produces non-positive long-run variance
        # (can happen with very high negative autocorrelation).
        return float(np.sqrt(gamma0 / T))
    return float(np.sqrt(lrv / T))


def _fmb_rho(panel: pd.DataFrame, feat: str, fwd: str, *, nw_lag: int
             ) -> Dict[str, float]:
    """Fama-MacBeth-style: per-date Spearman, mean across dates.

    Returns dict with both naive iid t and Newey-West HAC t (lag=nw_lag).
    """
    per, _ = _per_date_spearman(panel, feat, fwd)
    if len(per) < 5:
        return {"fmb_rho": float("nan"),
                "fmb_t_raw": float("nan"),
                "fmb_t_nw": float("nan"),
                "fmb_se_raw": float("nan"),
                "fmb_se_nw": float("nan"),
                "fmb_dates": len(per),
                "nw_lag": nw_lag}
    mean = float(per.mean())
    se_raw = float(per.std(ddof=1) / math.sqrt(len(per))) if per.std(ddof=1) > 0 else float("nan")
    t_raw = mean / se_raw if se_raw and not math.isnan(se_raw) else float("nan")
    se_nw = _newey_west_se(per, nw_lag)
    t_nw = mean / se_nw if se_nw and not math.isnan(se_nw) and se_nw > 0 else float("nan")
    return {"fmb_rho": mean,
            "fmb_t_raw": t_raw,
            "fmb_t_nw": t_nw,
            "fmb_se_raw": se_raw,
            "fmb_se_nw": se_nw,
            "fmb_dates": int(len(per)),
            "nw_lag": int(nw_lag)}


def _cluster_bootstrap_rho(panel: pd.DataFrame, feat: str, fwd: str,
                            *, n_boot: int = 100, seed: int = 13,
                            date_subsample: int = 5) -> Dict[str, float]:
    """Block bootstrap on cg_id (resample tokens with replacement, recompute FMB rho).

    Captures within-token serial dependence the per-date FMB misses. Returns
    bootstrap-mean rho and the 95% percentile CI.

    To keep this tractable: (1) subsample every `date_subsample`-th date
    (independent enough at 5d step for h-horizons up to 20d), (2) work in
    numpy via a long array keyed by (date, token) so each bootstrap is just
    an index selection + per-date rank-corr loop.
    """
    # Subsample dates for speed
    all_dates = np.sort(panel["date"].unique())
    keep_dates = all_dates[::date_subsample]
    sub = panel[panel["date"].isin(keep_dates)][["date", "cg_id", feat, fwd]].dropna()
    if len(sub) < 200:
        return {"boot_mean": float("nan"), "boot_lo": float("nan"),
                "boot_hi": float("nan"), "boot_n": 0}

    tokens = sub["cg_id"].unique()
    rng = np.random.default_rng(seed)
    samples = []
    # Pre-group by token for fast resampling — list of (feat, fwd) per token
    by_token: Dict[str, pd.DataFrame] = {tok: g for tok, g in sub.groupby("cg_id")}
    for _ in range(n_boot):
        sel = rng.choice(tokens, size=len(tokens), replace=True)
        parts = [by_token[t] for t in sel]
        boot = pd.concat(parts, ignore_index=True)
        per, _ = _per_date_spearman(boot, feat, fwd)
        if len(per) >= 5:
            samples.append(float(per.mean()))
    if not samples:
        return {"boot_mean": float("nan"), "boot_lo": float("nan"),
                "boot_hi": float("nan"), "boot_n": 0}
    arr = np.asarray(samples)
    return {"boot_mean": float(arr.mean()),
            "boot_lo":   float(np.quantile(arr, 0.025)),
            "boot_hi":   float(np.quantile(arr, 0.975)),
            "boot_n":    int(len(arr)),
            "date_subsample": int(date_subsample)}


# ----- in-sample ridge (with chronological CV, fixing MIT critique #8) --- #

def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    p = X.shape[1]
    I = np.eye(p); I[-1, -1] = 0.0
    return np.linalg.solve(X.T @ X + alpha * I, X.T @ y)


def _fit_sleeve_ridge_chrono(panel: pd.DataFrame, fwd: str) -> Dict[str, float]:
    """Ridge over the 4 sleeves, alpha picked by CHRONOLOGICAL 80/20 CV
    (the random split previously here is leakage-prone -- MIT critique #8)."""
    cols = SLEEVES
    sub = panel.sort_values("date")[["date"] + cols + [fwd]].dropna()
    if len(sub) < 500:
        return {c: float("nan") for c in cols}
    X = sub[cols].to_numpy(dtype=float)
    X = np.hstack([X, np.ones((len(X), 1))])
    y = sub[fwd].to_numpy(dtype=float)
    cut = int(0.8 * len(X))    # chronological
    Xtr, Xte = X[:cut], X[cut:]
    ytr, yte = y[:cut], y[cut:]
    best = None
    for a in (1.0, 10.0, 100.0, 1000.0):
        beta = _ridge_fit(Xtr, ytr, a)
        pred = Xte @ beta
        rx = pd.Series(pred).rank()
        ry = pd.Series(yte).rank()
        rho = float(np.corrcoef(rx, ry)[0, 1]) if rx.std() and ry.std() else float("nan")
        if best is None or (not math.isnan(rho) and rho > best[0]):
            best = (rho, a, beta)
    _, _, beta = best
    return {c: float(beta[i]) for i, c in enumerate(cols)}


# ----- weight rules used in the holdout evaluation ----------------------- #

def _theory_weights() -> Dict[str, float]:
    """Tier-A theory defaults (sleeve key -> weight). Matches overall_score.TIER_A_WEIGHTS."""
    return {"trend_cs": 0.40, "reversal_cs": 0.25, "breadth_cs": 0.15, "risk_cs": 0.10}


def _calibrated_weights_from_panel(
    panel: pd.DataFrame,
    horizon: int,
    *,
    mode: str = "drop",
    t_threshold: float = 2.0,
    use_nw: bool = True,
) -> Dict[str, float]:
    """Compute calibrated sleeve weights using ONLY this panel slice.

    This is the core "train-only" path: when called with the train slice it
    produces honest out-of-sample weights for holdout evaluation. Sleeve
    keys match `SLEEVES` (suffix "_cs"). TS sleeves are not included here
    because the panel doesn't carry them.
    """
    fwd = f"fwd_{horizon}d"
    nw_lag = horizon - 1
    raw_size: Dict[str, float] = {}
    for s in SLEEVES:
        r = _fmb_rho(panel, s, fwd, nw_lag=nw_lag)
        rho = r["fmb_rho"]
        t = r["fmb_t_nw"] if use_nw else r["fmb_t_raw"]
        if rho != rho or t != t or abs(t) < t_threshold:
            raw_size[s] = 0.0
            continue
        if rho < 0:
            if mode == "flip":
                raw_size[s] = abs(rho)
            else:
                raw_size[s] = 0.0
        else:
            raw_size[s] = abs(rho)
    total = sum(raw_size.values())
    learnable_budget = 0.90    # match overall_score (TS = 0.10 reserved)
    out: Dict[str, float] = {}
    if total <= 1e-12:
        for s in SLEEVES:
            out[s] = learnable_budget / 4.0
    else:
        for s in SLEEVES:
            out[s] = raw_size[s] / total * learnable_budget
    return out


# ----- composite-rho evaluation (the actual holdout metric) -------------- #

def _composite_rho_per_date(panel: pd.DataFrame, weights: Dict[str, float],
                            horizon: int) -> Tuple[np.ndarray, np.ndarray]:
    """Build composite = sum(w_s * sleeve_value_s), then per-date Spearman
    against fwd_{h}d. Returns (per_date_rho, date_array)."""
    fwd = f"fwd_{horizon}d"
    cols = SLEEVES
    sub = panel[["date"] + cols + [fwd]].dropna(subset=cols + [fwd]).copy()
    w = np.array([weights.get(c, 0.0) for c in cols])
    sub["__composite"] = sub[cols].to_numpy(dtype=float) @ w
    per_rho = []
    per_date = []
    for d, grp in sub.sort_values("date").groupby("date", sort=True):
        if len(grp) < 8:
            continue
        rx = grp["__composite"].rank()
        ry = grp[fwd].rank()
        if rx.std() == 0 or ry.std() == 0:
            continue
        per_rho.append(float(np.corrcoef(rx, ry)[0, 1]))
        per_date.append(pd.Timestamp(d))
    return np.asarray(per_rho), np.asarray(per_date, dtype="datetime64[ns]")


def _composite_fmb_summary(panel: pd.DataFrame, weights: Dict[str, float],
                            horizon: int) -> Dict[str, float]:
    per_rho, _ = _composite_rho_per_date(panel, weights, horizon)
    if len(per_rho) < 5:
        return {"rho": float("nan"), "t_raw": float("nan"),
                "t_nw": float("nan"), "n_dates": int(len(per_rho))}
    mean = float(per_rho.mean())
    sd = float(per_rho.std(ddof=1)) if per_rho.std(ddof=1) > 0 else float("nan")
    se_raw = sd / math.sqrt(len(per_rho)) if sd and not math.isnan(sd) else float("nan")
    t_raw = mean / se_raw if se_raw and not math.isnan(se_raw) else float("nan")
    se_nw = _newey_west_se(per_rho, horizon - 1)
    t_nw = mean / se_nw if se_nw and not math.isnan(se_nw) and se_nw > 0 else float("nan")
    return {"rho": mean, "t_raw": t_raw, "t_nw": t_nw,
            "n_dates": int(len(per_rho))}


def evaluate_oos_weights(panel: pd.DataFrame, horizon: int,
                          *, t_threshold: float = 2.0, use_nw: bool = True
                          ) -> Dict[str, dict]:
    """The chronologically-honest head-to-head.

    For a given horizon:
      1. Chronological 80/20 split.
      2. Fit calibrated sleeve weights on TRAIN ONLY (NW + t-threshold gate).
      3. Evaluate composite-vs-fwd Spearman rho on the HOLDOUT slice.
      4. Compare against fixed theory weights (Tier-A) computed on the same
         holdout slice.

    Returns a dict with both schemes' rho / t / n_dates, plus the actual
    weights used.
    """
    train, holdout, cutoff = _chronological_split(panel, TRAIN_FRAC)
    cal_weights = _calibrated_weights_from_panel(
        train, horizon, mode="drop", t_threshold=t_threshold, use_nw=use_nw)
    theory = _theory_weights()
    return {
        "horizon": horizon,
        "cutoff_date": str(cutoff.date()),
        "train_dates": int(train["date"].nunique()),
        "holdout_dates": int(holdout["date"].nunique()),
        "calibrated_weights_train_only": cal_weights,
        "theory_weights": theory,
        "holdout_calibrated": _composite_fmb_summary(holdout, cal_weights, horizon),
        "holdout_theory":     _composite_fmb_summary(holdout, theory, horizon),
        "in_sample_train_calibrated": _composite_fmb_summary(train, cal_weights, horizon),
        "in_sample_train_theory":     _composite_fmb_summary(train, theory, horizon),
    }


# ----- atomic-weighted trend sleeve (response to critique #6) ----------- #

def compute_atomic_weighted_sleeve(panel: pd.DataFrame, sleeve_atomics: Sequence[str],
                                    horizon: int, *, use_nw: bool = True,
                                    t_threshold: float = 2.0) -> Tuple[pd.Series, Dict[str, float]]:
    """Within-sleeve atomic re-weighting:
       1. For each atomic signal in `sleeve_atomics`, compute FMB rho on the
          full sample at the given horizon.
       2. Weight = |fmb_rho| if (NW t-stat passes threshold AND sign matches
          desired direction, i.e. positive). Drop sign-wrong atomics.
       3. Composite = weighted sum of CS-percentile values; weights sum to 1.

    Returns the composite series AND the atomic-weight dict.
    """
    fwd = f"fwd_{horizon}d"
    nw_lag = horizon - 1
    weights: Dict[str, float] = {}
    for a in sleeve_atomics:
        if a not in panel.columns:
            continue
        r = _fmb_rho(panel, a, fwd, nw_lag=nw_lag)
        rho = r["fmb_rho"]
        t = r["fmb_t_nw"] if use_nw else r["fmb_t_raw"]
        if rho != rho or t != t:
            continue
        if abs(t) < t_threshold:
            continue
        if rho < 0:           # sign-wrong -> drop
            continue
        weights[a] = abs(rho)
    total = sum(weights.values())
    if total <= 1e-12:
        return pd.Series(index=panel.index, dtype=float), {}
    for k in weights:
        weights[k] /= total
    cols = list(weights.keys())
    arr = panel[cols].to_numpy(dtype=float)
    w = np.array([weights[c] for c in cols])
    composite = pd.Series(arr @ w, index=panel.index)
    return composite, weights


def trend_sleeve_atomic_reweight_eval(panel: pd.DataFrame, horizon: int,
                                       use_nw: bool = True,
                                       t_threshold: float = 2.0) -> Dict[str, object]:
    """Build atomic-reweighted trend composite using ONLY train slice, then
    evaluate against fwd returns on the holdout. Answers: "if we don't drop
    trend, but re-weight its atomics, does it become net positive?"
    """
    train, holdout, cutoff = _chronological_split(panel, TRAIN_FRAC)
    # Fit weights on train
    _, w = compute_atomic_weighted_sleeve(train, TREND_ATOMICS, horizon,
                                           use_nw=use_nw, t_threshold=t_threshold)
    if not w:
        return {"horizon": horizon, "atomic_weights": {},
                "holdout": {"rho": float("nan")},
                "equal_weight_holdout": {"rho": float("nan")},
                "note": "no atomic survived the gate on train slice"}

    # Build composite on the HOLDOUT slice using train weights
    cols = list(w.keys())
    arr = holdout[cols].to_numpy(dtype=float)
    wvec = np.array([w[c] for c in cols])
    holdout = holdout.copy()
    holdout["__atomic_trend"] = arr @ wvec
    rho_re = _composite_fmb_summary(
        holdout.rename(columns={"__atomic_trend": "__cmp"})[["date", "__cmp", f"fwd_{horizon}d"]]
              .assign(trend_cs=lambda d: d["__cmp"], reversal_cs=0, breadth_cs=0, risk_cs=0),
        weights={"trend_cs": 1.0, "reversal_cs": 0, "breadth_cs": 0, "risk_cs": 0},
        horizon=horizon)

    rho_eq = _composite_fmb_summary(
        holdout[["date", "trend_cs", f"fwd_{horizon}d"]]
              .assign(reversal_cs=0, breadth_cs=0, risk_cs=0),
        weights={"trend_cs": 1.0, "reversal_cs": 0, "breadth_cs": 0, "risk_cs": 0},
        horizon=horizon)

    return {
        "horizon": horizon,
        "cutoff_date": str(cutoff.date()),
        "atomic_weights": w,
        "holdout_atomic_reweight": rho_re,
        "holdout_equal_weight_sleeve": rho_eq,
        "delta_rho_vs_equal": float(rho_re["rho"]) - float(rho_eq["rho"])
            if not math.isnan(rho_re["rho"]) and not math.isnan(rho_eq["rho"]) else float("nan"),
    }


# ----- simulated long-short portfolio Sharpe / turnover ----------------- #

def simulate_long_short(panel: pd.DataFrame, weights: Dict[str, float],
                         horizon: int, *, top_q: float = 0.2, bot_q: float = 0.2
                         ) -> Dict[str, float]:
    """Build a daily composite, on each date long the top-quintile of composite
    and short the bottom-quintile. Compute h-day forward log-return per
    rebalance. Average, scale to ~annual Sharpe, and report turnover.

    NB: positions are rebalanced daily (not every h days), so this is an
    upper bound on traded Sharpe -- but it gives a sense of capacity /
    realism. Turnover is reported as the average fraction of names whose
    long/short status flips day-over-day.
    """
    fwd = f"fwd_{horizon}d"
    cols = SLEEVES
    sub = panel[["date", "cg_id"] + cols + [fwd]].dropna(subset=cols + [fwd]).copy()
    w = np.array([weights.get(c, 0.0) for c in cols])
    sub["__composite"] = sub[cols].to_numpy(dtype=float) @ w

    # Per-date deciles
    by_day = []
    flip_rates = []
    prev_long = None
    prev_short = None
    for d, grp in sub.sort_values("date").groupby("date", sort=True):
        if len(grp) < 20:
            continue
        thi = grp["__composite"].quantile(1 - top_q)
        tlo = grp["__composite"].quantile(bot_q)
        longs = set(grp.loc[grp["__composite"] >= thi, "cg_id"].tolist())
        shorts = set(grp.loc[grp["__composite"] <= tlo, "cg_id"].tolist())
        if not longs or not shorts:
            continue
        ret_long = grp.loc[grp["cg_id"].isin(longs), fwd].mean()
        ret_short = grp.loc[grp["cg_id"].isin(shorts), fwd].mean()
        ls = float(ret_long - ret_short)
        by_day.append(ls)
        if prev_long is not None:
            # symmetric difference / union ~ flip rate
            u = len(longs | prev_long) + len(shorts | prev_short)
            s = len(longs ^ prev_long) + len(shorts ^ prev_short)
            flip_rates.append(s / max(1, u))
        prev_long = longs
        prev_short = shorts

    if len(by_day) < 30:
        return {"sharpe_annual": float("nan"), "mean_ret_per_h": float("nan"),
                "turnover_avg": float("nan"), "n_days": len(by_day)}

    arr = np.asarray(by_day, dtype=float)
    # Rebalance is daily; each "return" is h-day forward. Scale:
    # daily Sharpe = mean / std (since each return is h-day, we approximate
    # annualisation by sqrt(365/h) -- accounts for the embedded horizon).
    mean_d = float(arr.mean())
    sd_d = float(arr.std(ddof=1))
    if sd_d <= 0:
        sharpe = float("nan")
    else:
        # Per-period Sharpe times sqrt(periods_per_year_at_h_horizon)
        sharpe = (mean_d / sd_d) * math.sqrt(365.0 / horizon)
    return {
        "sharpe_annual": sharpe,
        "mean_ret_per_h": mean_d,
        "sd_ret_per_h": sd_d,
        "turnover_avg": float(np.mean(flip_rates)) if flip_rates else float("nan"),
        "n_days": int(len(arr)),
        "horizon": horizon,
    }


# ----- main --------------------------------------------------------------- #

def main(force_rebuild: bool = False):
    print(f"loading {SCORES_HISTORY}")
    history = pd.read_csv(SCORES_HISTORY, parse_dates=["date"])
    history = history.dropna(subset=["trend_cs_percentile", "reversal_cs_percentile"])
    print(f"  rows={len(history):,} tokens={history.cg_id.nunique()} "
          f"dates={history.date.nunique()}")

    panel = _load_or_build_panel(history, force=force_rebuild)
    if panel.empty:
        print("panel empty — aborting")
        return

    train_full, holdout_full, cutoff = _chronological_split(panel, TRAIN_FRAC)
    print(f"  chronological split: train < {cutoff.date()} | "
          f"train_dates={train_full.date.nunique()} | "
          f"holdout_dates={holdout_full.date.nunique()}")

    # ---- per-horizon, per-feature stats (FULL sample, with NW t) ----------
    print("\ncomputing per-horizon FMB rho (Newey-West HAC SE, lag = h-1) ...")
    horizons_out: Dict[str, dict] = {}
    for h in HORIZONS:
        fwd = f"fwd_{h}d"
        nw_lag = h - 1
        print(f"  horizon={h}d (nw lag={nw_lag})")
        feat_stats: Dict[str, dict] = {}
        for feat in FEATURE_COLS:
            if feat not in panel.columns:
                continue
            row_full  = _fmb_rho(panel, feat, fwd, nw_lag=nw_lag)
            row_train = _fmb_rho(train_full, feat, fwd, nw_lag=nw_lag)
            feat_stats[feat] = {
                # Backward-compat fields:
                "fmb_rho": row_full["fmb_rho"],
                "fmb_t":   row_full["fmb_t_raw"],
                "fmb_dates": row_full["fmb_dates"],
                # NEW v2 fields:
                "fmb_t_raw": row_full["fmb_t_raw"],
                "fmb_t_nw":  row_full["fmb_t_nw"],
                "fmb_se_raw": row_full["fmb_se_raw"],
                "fmb_se_nw":  row_full["fmb_se_nw"],
                "nw_lag": row_full["nw_lag"],
                # Train-only stats (used for honest weight calibration):
                "fmb_rho_train": row_train["fmb_rho"],
                "fmb_t_raw_train": row_train["fmb_t_raw"],
                "fmb_t_nw_train":  row_train["fmb_t_nw"],
                "fmb_dates_train": row_train["fmb_dates"],
                # Bonferroni gate
                "bonferroni_t_threshold": BONFERRONI_T,
                "passes_bonferroni_nw": bool(
                    row_full["fmb_t_nw"] == row_full["fmb_t_nw"]
                    and abs(row_full["fmb_t_nw"]) >= BONFERRONI_T),
                "passes_bonferroni_nw_train": bool(
                    row_train["fmb_t_nw"] == row_train["fmb_t_nw"]
                    and abs(row_train["fmb_t_nw"]) >= BONFERRONI_T),
            }
        sleeve_ridge = _fit_sleeve_ridge_chrono(panel, fwd)
        sleeve_rho = {s: feat_stats[s]["fmb_rho"] for s in SLEEVES if s in feat_stats}
        horizons_out[f"{h}d"] = {
            "features": feat_stats,
            "sleeve_ridge_coefs": sleeve_ridge,
            "sleeve_fmb_rho": sleeve_rho,
        }

    # ---- cluster bootstrap on cg_id for sleeves (slow but informative) ----
    print("\ncluster bootstrap (100 reps over cg_id, every-5th-date subsample) "
          "for the 4 sleeves at 5d / 60d ...", flush=True)
    cluster_boot: Dict[str, dict] = {}
    for h in (5, 60):    # subset for speed
        fwd = f"fwd_{h}d"
        cluster_boot[f"{h}d"] = {}
        for s in SLEEVES:
            try:
                cb = _cluster_bootstrap_rho(panel, s, fwd, n_boot=100, seed=13 + h)
            except Exception as e:
                cb = {"error": str(e)}
            cluster_boot[f"{h}d"][s] = cb
            print(f"  {h}d {s:14s}  mean={cb.get('boot_mean', float('nan')):+.4f}  "
                  f"CI=[{cb.get('boot_lo', float('nan')):+.4f}, "
                  f"{cb.get('boot_hi', float('nan')):+.4f}]  n={cb.get('boot_n')}")

    # ---- walk-forward chronological holdout evaluation --------------------
    print("\nchronological holdout evaluation (train-only weights, holdout rho) ...")
    holdout_results: Dict[str, dict] = {}
    for h in HORIZONS:
        for thr_label, thr in (("t2", 2.0), ("bonferroni", BONFERRONI_T)):
            res = evaluate_oos_weights(panel, h, t_threshold=thr, use_nw=True)
            holdout_results[f"{h}d_{thr_label}"] = res
            cw = res["calibrated_weights_train_only"]
            print(f"  {h}d threshold={thr_label}: cal weights = "
                  f"{ {k: round(v,3) for k,v in cw.items()} }")
            print(f"    holdout cal rho={res['holdout_calibrated']['rho']:+.4f} "
                  f"(t_nw={res['holdout_calibrated']['t_nw']:+.2f}) | "
                  f"theory rho={res['holdout_theory']['rho']:+.4f} "
                  f"(t_nw={res['holdout_theory']['t_nw']:+.2f})")

    # ---- atomic-weighted trend sleeve evaluation --------------------------
    print("\natomic re-weighting eval for trend sleeve ...")
    trend_atomic = {}
    for h in HORIZONS:
        r = trend_sleeve_atomic_reweight_eval(panel, h, use_nw=True, t_threshold=2.0)
        trend_atomic[f"{h}d"] = r
        if r.get("atomic_weights"):
            print(f"  {h}d  re-weighted holdout rho="
                  f"{r['holdout_atomic_reweight']['rho']:+.4f} | "
                  f"equal-weight holdout rho="
                  f"{r['holdout_equal_weight_sleeve']['rho']:+.4f} | "
                  f"delta={r['delta_rho_vs_equal']:+.4f}")
        else:
            print(f"  {h}d  no atomic survived the gate on train")

    # ---- simulated long-short Sharpe / turnover ---------------------------
    print("\nlong-short simulation (top quintile - bottom quintile, 5d / 60d, "
          "calibrated train-only weights) ...")
    sharpe_summary: Dict[str, dict] = {}
    for h in (5, 60):
        cal = holdout_results[f"{h}d_t2"]["calibrated_weights_train_only"]
        theory = _theory_weights()
        s_cal = simulate_long_short(holdout_full, cal, h)
        s_thy = simulate_long_short(holdout_full, theory, h)
        sharpe_summary[f"{h}d"] = {"calibrated": s_cal, "theory": s_thy}
        print(f"  {h}d cal Sharpe={s_cal['sharpe_annual']:+.2f} turnover={s_cal['turnover_avg']:+.3f}  "
              f"| theory Sharpe={s_thy['sharpe_annual']:+.2f} turnover={s_thy['turnover_avg']:+.3f}")

    # ---- survivorship audit -----------------------------------------------
    pct = panel.groupby("date")["cg_id"].nunique()
    today_n = int(pct.iloc[-1]) if len(pct) else 0
    start_n = int(pct.iloc[0]) if len(pct) else 0
    inflate = today_n - start_n
    survivorship = {
        "scores_history_first_date_tokens": int(history[history.date == history.date.min()].cg_id.nunique()),
        "scores_history_last_date_tokens":  int(history[history.date == history.date.max()].cg_id.nunique()),
        "indicator_panel_first_date_tokens": start_n,
        "indicator_panel_last_date_tokens":  today_n,
        "added_later_count": int(inflate),
        "delisted_count": 0,
        "warning": (
            f"{today_n} tokens alive on last date; 0 delisted in the sample. "
            "Universe is survivorship-biased: tokens that died before today are "
            "absent. Calibrated rho/weights overstate live edge."
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "schema_version": 2,
        "split": {"train_frac": TRAIN_FRAC,
                  "cutoff_date": str(cutoff.date()),
                  "n_train_dates": int(train_full.date.nunique()),
                  "n_holdout_dates": int(holdout_full.date.nunique())},
        "horizons": horizons_out,
        "feature_cols": FEATURE_COLS,
        "sleeves": SLEEVES,
        "n_panel_rows": int(len(panel)),
        "n_dates": int(panel["date"].nunique()),
        "n_tokens": int(panel["cg_id"].nunique()),
        "survivorship": survivorship,
        "cluster_bootstrap": cluster_boot,
        "multiple_comparison": {
            "n_tests": N_TESTS_FAMILY,
            "bonferroni_alpha_0.05": BONFERRONI_T,
            "note": "20 features x 4 horizons = 80 simultaneous tests; "
                    "|t|>=3.16 (z-approx for alpha=0.05/80) needed family-wise.",
        },
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nwrote {OUT_PATH}")

    holdout_payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "schema_version": 2,
        "split": payload["split"],
        "horizons_evaluated": HORIZONS,
        "results": holdout_results,
        "trend_atomic_reweight": trend_atomic,
        "sharpe_simulation": sharpe_summary,
        "notes": [
            "Calibrated weights are fit on the train slice only "
            "(date < cutoff). Holdout rho is composite vs fwd_h on the "
            "remaining 20% of dates.",
            "All t-stats use Newey-West HAC SE with lag = h - 1.",
            "Threshold variants reported: t2 (|t_nw| >= 2.0, naive) and "
            "bonferroni (|t_nw| >= 3.16 for 80-test family).",
        ],
    }
    HOLDOUT_PATH.write_text(json.dumps(holdout_payload, indent=2, default=str))
    print(f"wrote {HOLDOUT_PATH}")

    # ---- pretty print summary ---------------------------------------------
    print("\n=== Per-sleeve FMB rho with raw vs NW t (full sample) ===")
    header = f"{'sleeve':14s}" + "".join(f"  {h}d (rho/t_raw/t_nw)".rjust(30) for h in HORIZONS)
    print(header)
    for s in SLEEVES:
        line = f"{s:14s}"
        for h in HORIZONS:
            r = horizons_out[f"{h}d"]["features"].get(s, {})
            line += (f"  {r.get('fmb_rho', float('nan')):+.4f}/"
                     f"{r.get('fmb_t_raw', float('nan')):+.2f}/"
                     f"{r.get('fmb_t_nw', float('nan')):+.2f}").rjust(30)
        print(line)
    print(f"\n survivorship: {survivorship['warning']}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force_rebuild=force)
