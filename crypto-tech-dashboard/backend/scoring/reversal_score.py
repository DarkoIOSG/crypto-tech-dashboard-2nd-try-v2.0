"""Reversal strength scoring — Plan section 5.2, 7 signals.

Signal table (Plan):
    RSI oversold dist      (rsi_dist_os_14, positive = more oversold)
    RSI turn event         (rsi_turn_event_14)
    KDJ oversold dist      (kdj_os_distance, positive when J<20)
    Bollinger Z (negated)  (-bb_z_20)
    MR Z                   (mr_z_40_skip16)
    MA50 dev z (negated)   (-ma50_dev_z_40)
    Short negative mom     (-mom_ret_5d)
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

import pandas as pd


# Signals are 2-tuples (key, sign) — sign=-1 means negate before scoring.
REVERSAL_SIGNALS = [
    ("rsi_dist_os_14", 1.0),
    ("rsi_turn_event_14", 1.0),
    ("kdj_os_distance", 1.0),
    ("bb_z_20", -1.0),
    ("mr_z_40_skip16", 1.0),
    ("ma50_dev_z_40", -1.0),
    ("mom_ret_5d", -1.0),
]


def _scalar(value) -> float:
    if value is None:
        return 0.0
    f = float(value)
    if f != f:
        return 0.0
    return f


def compute_reversal_score(
    indicators: Mapping[str, object],
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Weighted average of signed reversal signals for one token."""
    w = {k: 1.0 for k, _ in REVERSAL_SIGNALS}
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    total = 0.0
    used = 0.0
    for key, sign in REVERSAL_SIGNALS:
        weight = w.get(key, 0.0)
        val = _scalar(indicators.get(key)) * sign * weight
        total += val
        used += weight
    if used == 0.0:
        return 0.0
    return total / used


def compute_reversal_components(
    indicators: Mapping[str, object]
) -> Dict[str, float]:
    """Return signed raw values for each reversal signal (for UI display)."""
    out: Dict[str, float] = {}
    for key, sign in REVERSAL_SIGNALS:
        out[key] = _scalar(indicators.get(key)) * sign
    return out


def cross_sectional_reversal_scores(
    all_indicators: Mapping[str, Mapping[str, object]],
    weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Per-token 0-100 reversal score using cross-sectional percentile rank."""
    if not all_indicators:
        return {}

    w = {k: 1.0 for k, _ in REVERSAL_SIGNALS}
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    rows = {}
    for token_id, ind in all_indicators.items():
        rec: Dict[str, float] = {}
        for key, sign in REVERSAL_SIGNALS:
            rec[key] = _scalar(ind.get(key)) * sign
        rows[token_id] = rec
    df = pd.DataFrame.from_dict(rows, orient="index")

    pct_frame = df.rank(pct=True) * 100.0

    weighted_sum = pd.Series(0.0, index=pct_frame.index)
    weight_sum = 0.0
    for key, _ in REVERSAL_SIGNALS:
        wt = float(w.get(key, 0.0))
        if wt == 0.0:
            continue
        weighted_sum = weighted_sum + pct_frame[key].fillna(50.0) * wt
        weight_sum += wt
    if weight_sum == 0.0:
        return {tid: 0.0 for tid in df.index}

    out = (weighted_sum / weight_sum).to_dict()
    return {k: float(v) for k, v in out.items()}
