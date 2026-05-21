"""R8-2A: Tier-A Overall composite score (Phase-2 items 2 + 9).

Blends the Trend / Reversal CS percentiles + 4 additional sleeves into one
0-100 headline number. The weights are finance-theory priors (not learned —
Tier B will replace them via Ridge regression in Phase 2D).

Formula (per user Q1 + Q7):
    Overall = 0.40 · Trend                   (CS percentile)
            + 0.25 · Reversal                (CS percentile)
            + 0.15 · Breadth                 (CS-ranked % of 9 trend
                                              signals that are positive)
            + 0.10 · Risk                    (CS-ranked inverse 20d vol)
            + 0.05 · TS_Trend_2y             (rolling 2-yr time-series
                                              percentile of trend_score)
            + 0.05 · TS_Reversal_2y          (same for reversal_score)

Weight rationale (Liu/Tsyvinski 2021, Russell/Engle 2010):
    - momentum (Trend 0.40) is the most empirically robust factor in
      crypto.
    - reversal (0.25) is real but noisier.
    - signal breadth (0.15) is a confirmation discount — high score
      should require multiple sub-signals agreeing.
    - risk-adjustment (0.10) penalises high-vol moonshots.
    - long-history TS percentiles (5% each) catch rare-strength outliers
      that recent CS-only scores miss.

The breakdown / sleeve view that the UI shows is 6 rows (per user Q7):
    Trend, Reversal, Signal Breadth, Risk, Trend TS 2y, Reversal TS 2y

Each row has fields: {sleeve, value (0-100), weight, contribution}.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

import pandas as pd

from backend.scoring.ranking import cross_sectional_percentile
from backend.scoring.trend_score import TREND_SIGNALS


# Tier-A weights — finance-theory priors. Sum to 1.0.
TIER_A_WEIGHTS: Dict[str, float] = {
    "trend":          0.40,
    "reversal":       0.25,
    "breadth":        0.15,
    "risk":           0.10,
    "ts_trend_2y":    0.05,
    "ts_reversal_2y": 0.05,
}


def load_tier_b_weights() -> Optional[Dict[str, float]]:
    """R8-4A: data-driven weights from scripts/train_tier_b.py, if accepted.

    Returns None when the training script either hasn't run, didn't accept
    (holdout Spearman ρ failed the +0.02 gate over Tier-A), or wrote a
    malformed file. Callers MUST fall back to TIER_A_WEIGHTS when None.
    """
    import json
    from backend.config import DATA_DIR

    path = DATA_DIR / "scoring" / "tier_b_weights.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    if not payload.get("accept"):
        return None
    weights = payload.get("weights")
    if not isinstance(weights, dict):
        return None
    # Must contain every sleeve we score on.
    required = set(TIER_A_WEIGHTS.keys())
    if not required.issubset(weights.keys()):
        return None
    return {k: float(weights[k]) for k in required}


def resolve_weights(mode: str = "theory") -> Dict[str, float]:
    """`mode` ∈ {"theory", "calibrated", "regressed"}.

    - "theory":     Tier-A finance-prior weights (default).
    - "calibrated": Data-driven weights from
                    `backend.scoring.calibrated_weights` (sized to
                    |fmb_rho|, sign-respecting; drops sleeves whose
                    empirical sign disagrees with the score's intent).
    - "regressed":  Tier-B Ridge weights (only if the trainer accepted).

    Falls back to Tier A on any failure so the live UI never breaks.
    """
    if mode == "regressed":
        wb = load_tier_b_weights()
        if wb is not None:
            return wb
    if mode == "calibrated":
        # Lazy import to avoid a hard cycle with backend.config / DATA_DIR.
        from backend.scoring.calibrated_weights import load_calibrated_weights
        wc = load_calibrated_weights()
        if wc is not None:
            return wc
    return dict(TIER_A_WEIGHTS)


def resolve_contribution_signs(mode: str = "theory") -> Dict[str, int]:
    """Per-sleeve contribution sign (+1 normal, -1 flipped for mode='flip').

    Used when a calibrated sleeve has rho<0 but the operator chose to flip
    its contribution rather than drop it. For "theory" / "regressed" /
    "calibrated"+mode='drop', all signs are +1.
    """
    if mode == "calibrated":
        from backend.scoring.calibrated_weights import load_contribution_signs
        return load_contribution_signs()
    return {k: +1 for k in TIER_A_WEIGHTS}


def _safe(v) -> float:
    """Coerce to float, NaN/None -> 0.0."""
    if v is None:
        return 0.0
    f = float(v)
    return 0.0 if f != f else f


def _safe_or_neutral(v) -> float:
    """Like _safe but maps missing/None to 50.0 (neutral percentile).

    Used for the TS-history sleeves where short-history tokens legitimately
    return None — penalising them to 0 would be wrong.
    """
    if v is None:
        return 50.0
    f = float(v)
    return 50.0 if f != f else f


def compute_breadth(trend_components: Mapping[str, object]) -> float:
    """% of 9 trend signals that are strictly positive (0-100 scalar).

    Computed per-token from compute_trend_components output. Cross-sectional
    ranking of this scalar across tokens happens upstream (so the breadth
    sleeve fed into the formula is itself a percentile).
    """
    pos = 0
    total = 0
    for sig in TREND_SIGNALS:
        if sig in trend_components:
            total += 1
            val = trend_components.get(sig)
            if val is not None and float(val) > 0.0:
                pos += 1
    return 100.0 * pos / total if total > 0 else 0.0


def cross_sectional_breadth(
    components_by_token: Mapping[str, Mapping[str, object]],
) -> Dict[str, float]:
    """Returns {cg_id: breadth_pct_0_to_100} as a CS percentile rank.

    Higher score = more of this token's signals are positive RELATIVE to
    the universe today.
    """
    raw = {cg_id: compute_breadth(cmp) for cg_id, cmp in components_by_token.items()}
    return cross_sectional_percentile(raw)


def cross_sectional_risk(
    indicators_by_token: Mapping[str, Mapping[str, object]],
    vol_key: str = "vol_20d",
) -> Dict[str, float]:
    """Inverse-volatility CS percentile (0-100). Low vol -> high score.

    indicators_by_token is the {cg_id: indicators_dict} the scoring
    pipeline already builds. We pull vol_{20d} (from the new VolatilityFamily)
    and invert before percentile-ranking.
    """
    raw: Dict[str, float] = {}
    for cg_id, ind in indicators_by_token.items():
        v = ind.get(vol_key)
        if v is None or float(v) != float(v):  # missing or NaN
            continue
        f = float(v)
        if f <= 0:
            continue
        raw[cg_id] = -f   # negate so low vol -> high rank
    return cross_sectional_percentile(raw)


def compute_overall_score(
    trend_cs_pct: float,
    reversal_cs_pct: float,
    breadth_cs_pct: float,
    risk_cs_pct: float,
    ts_trend_2y_pct: Optional[float],
    ts_reversal_2y_pct: Optional[float],
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Single-token composite. Returns 0-100 score."""
    w = dict(TIER_A_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    return (
        w["trend"]          * _safe(trend_cs_pct)
        + w["reversal"]     * _safe(reversal_cs_pct)
        + w["breadth"]      * _safe(breadth_cs_pct)
        + w["risk"]         * _safe(risk_cs_pct)
        + w["ts_trend_2y"]  * _safe_or_neutral(ts_trend_2y_pct)
        + w["ts_reversal_2y"] * _safe_or_neutral(ts_reversal_2y_pct)
    )


def compute_overall_components(
    *,
    trend_cs_pct: float,
    reversal_cs_pct: float,
    breadth_cs_pct: float,
    risk_cs_pct: float,
    ts_trend_2y_pct: Optional[float],
    ts_reversal_2y_pct: Optional[float],
    weights: Optional[Mapping[str, float]] = None,
) -> list:
    """Per-token sleeve breakdown for the UI.

    Returns the 6 sleeve rows in canonical display order:
        Trend / Reversal / Signal Breadth / Risk / TS Trend 2y / TS Rev 2y
    Each row: {sleeve, label, value, weight, contribution}.
    value is the sleeve's 0-100 percentile; contribution = value * weight.
    """
    w = dict(TIER_A_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})
    rows = [
        ("trend",          "Trend",            _safe(trend_cs_pct)),
        ("reversal",       "Reversal",         _safe(reversal_cs_pct)),
        ("breadth",        "Signal Breadth",   _safe(breadth_cs_pct)),
        ("risk",           "Risk (low vol)",   _safe(risk_cs_pct)),
        ("ts_trend_2y",    "Trend TS 2y",      _safe_or_neutral(ts_trend_2y_pct)),
        ("ts_reversal_2y", "Reversal TS 2y",   _safe_or_neutral(ts_reversal_2y_pct)),
    ]
    return [
        {
            "sleeve": k,
            "label": label,
            "value": value,
            "weight": w[k],
            "contribution": value * w[k],
        }
        for (k, label, value) in rows
    ]


def cross_sectional_overall_scores(
    *,
    indicators_by_token: Mapping[str, Mapping[str, object]],
    trend_cs_percentiles: Mapping[str, float],
    reversal_cs_percentiles: Mapping[str, float],
    components_by_token: Mapping[str, Mapping[str, object]],
    ts_trend_2y_by_token: Optional[Mapping[str, Optional[float]]] = None,
    ts_reversal_2y_by_token: Optional[Mapping[str, Optional[float]]] = None,
    weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Compute the Overall score for every token in the universe.

    Implementation order:
      1. Cross-sectionally rank breadth + risk (the new sleeves) so they
         live on the same 0-100 scale as trend / reversal.
      2. Blend the 6 sleeves per-token via the Tier-A weights.

    Returns {cg_id: overall_0_to_100}.
    """
    breadth_pct = cross_sectional_breadth(components_by_token)
    risk_pct = cross_sectional_risk(indicators_by_token)
    ts_trend = ts_trend_2y_by_token or {}
    ts_rev = ts_reversal_2y_by_token or {}

    out: Dict[str, float] = {}
    for cg_id in indicators_by_token.keys():
        out[cg_id] = compute_overall_score(
            trend_cs_pct=trend_cs_percentiles.get(cg_id, 0.0),
            reversal_cs_pct=reversal_cs_percentiles.get(cg_id, 0.0),
            breadth_cs_pct=breadth_pct.get(cg_id, 0.0),
            risk_cs_pct=risk_pct.get(cg_id, 0.0),
            ts_trend_2y_pct=ts_trend.get(cg_id),
            ts_reversal_2y_pct=ts_rev.get(cg_id),
            weights=weights,
        )
    return out
