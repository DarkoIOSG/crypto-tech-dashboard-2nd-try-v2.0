"""Ranking utilities — cross-sectional and time-series percentiles.

Plan section 5.3:
- cross_sectional_percentile(scores) -> per-token percentile in [0,100].
- time_series_percentile(history, window_days) -> rolling Series of percentile.
"""

from __future__ import annotations

from typing import Dict, Mapping

import numpy as np
import pandas as pd


def cross_sectional_percentile(
    scores: Mapping[str, float],
) -> Dict[str, float]:
    """Per-token percentile rank (0..100) across all tokens passed."""
    if not scores:
        return {}
    s = pd.Series(scores, dtype=float)
    pct = s.rank(pct=True) * 100.0
    return {k: float(v) for k, v in pct.to_dict().items()}


def time_series_percentile(history: pd.Series, window_days: int) -> pd.Series:
    """Rolling percentile rank of the **current** value within the last
    `window_days` observations.

    For each index t, output[t] = % of values in history[t-window+1 .. t]
    that are <= history[t]. Range [0, 100].
    """
    if history is None or len(history) == 0:
        return pd.Series(dtype=float)
    h = history.astype(float)

    def _last_pct(arr: np.ndarray) -> float:
        if arr is None or len(arr) == 0:
            return 0.0
        last = arr[-1]
        if np.isnan(last):
            return np.nan
        finite = arr[~np.isnan(arr)]
        if len(finite) == 0:
            return np.nan
        return float((finite <= last).sum()) / float(len(finite)) * 100.0

    return h.rolling(window=window_days, min_periods=1).apply(_last_pct, raw=True)


def current_time_series_percentile(history: pd.Series, window_days: int) -> float:
    """Convenience: percentile of the LAST value in history within the last
    `window_days` observations.

    Returns a single float in [0,100], or 0 if input empty.
    """
    if history is None or len(history) == 0:
        return 0.0
    tail = history.iloc[-window_days:].dropna()
    if len(tail) == 0:
        return 0.0
    last = float(tail.iloc[-1])
    return float((tail <= last).sum()) / float(len(tail)) * 100.0
