"""Trend strength scoring — Plan section 5.1, 9 signals.

Inputs:
    indicators: dict[str, scalar] — last-row values for one token. Should
                include the 9 signal keys below.
    weights:    optional dict[str, float] — defaults to 1.0 each.

Output:
    The function returns the **raw weighted sum** of signal values; callers
    cross-sectionally percentile-rank across tokens to produce the 0-100 score
    (see scoring/ranking.py). For a single token in isolation, the raw sum is
    still informative as a relative scalar.

NB: no try/except per hard rules. If keys are missing, treat them as 0.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

import pandas as pd


TREND_SIGNALS = [
    "mom_ret_10d",
    "mom_ret_20d",
    "macd_hist_12_26_9",
    "macd_hist_slope5_12_26_9",
    "sma_cross_strength_signed_5_20",
    "ema_cross_strength_signed_5_20",
    "ma50_slope_20d",
    "ma50_dev",
    "bb_pctb_20",
]


def _scalar(value) -> float:
    """Coerce to float; treat None / NaN as 0.0."""
    if value is None:
        return 0.0
    f = float(value)
    if f != f:  # NaN check without importing math
        return 0.0
    return f


def compute_trend_score(
    indicators: Mapping[str, object],
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Weighted sum of trend signals for one token (raw scalar).

    The cross-sectional percentile step is done by `scoring/ranking.py` after
    aggregating scores across all tokens.
    """
    w = {k: 1.0 for k in TREND_SIGNALS}
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    total = 0.0
    used = 0.0
    for sig in TREND_SIGNALS:
        weight = w.get(sig, 0.0)
        val = _scalar(indicators.get(sig)) * weight
        total += val
        used += weight

    if used == 0.0:
        return 0.0
    return total / used


def compute_trend_components(indicators: Mapping[str, object]) -> Dict[str, float]:
    """Return the raw scalar value for each trend signal (for UI display)."""
    return {sig: _scalar(indicators.get(sig)) for sig in TREND_SIGNALS}


def cross_sectional_trend_scores(
    all_indicators: Mapping[str, Mapping[str, object]],
    weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Compute cross-sectional 0-100 trend score across many tokens.

    Per Plan: for each signal, rank-pct across tokens (0..100). Then equal
    weight the percentiles. Returns {token_id: score_0_to_100}.
    """
    if not all_indicators:
        return {}

    w = {k: 1.0 for k in TREND_SIGNALS}
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    # Build a tokens x signals frame of raw values.
    rows = {}
    for token_id, ind in all_indicators.items():
        rows[token_id] = {sig: _scalar(ind.get(sig)) for sig in TREND_SIGNALS}
    df = pd.DataFrame.from_dict(rows, orient="index")

    pct_frame = df.rank(pct=True) * 100.0

    weighted_sum = pd.Series(0.0, index=pct_frame.index)
    weight_sum = 0.0
    for sig in TREND_SIGNALS:
        wt = float(w.get(sig, 0.0))
        if wt == 0.0:
            continue
        weighted_sum = weighted_sum + pct_frame[sig].fillna(50.0) * wt
        weight_sum += wt
    if weight_sum == 0.0:
        return {tid: 0.0 for tid in df.index}

    out = (weighted_sum / weight_sum).to_dict()
    return {k: float(v) for k, v in out.items()}
