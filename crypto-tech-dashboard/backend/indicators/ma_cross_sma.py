"""SMA-crossover family — ported from notebook cell 12 lines ~340-450.

Key formulas (closely matching `compute_features`):
  sma_fast = Close.rolling(fast).mean()
  sma_slow = Close.rolling(slow).mean()
  diff     = (sma_fast - sma_slow) / Close            # normalised to price
  prox     = 1 / (1 + |diff| / 0.01)                  # rational proximity
  slope10  = simple log-price 10-day slope (gate>0 keeps the bullish side)
  gate     = (slope10 > 0)
  cross_strength_signed = prox * sign(diff) * gate
  cross_up   = (diff[t-1] <= 0) AND (diff[t] > 0)
  cross_down = (diff[t-1] >= 0) AND (diff[t] < 0)
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class SMACrossFamily(IndicatorFamily):
    name = "sma_cross"
    default_params = {"fast": 5, "slow": 20, "scale": 0.01, "slope_window": 10}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        fast = int(p["fast"])
        slow = int(p["slow"])
        scale = float(p["scale"])
        slope_win = int(p["slope_window"])

        close = df["close"].astype(float)

        sma_fast = close.rolling(fast, min_periods=fast).mean()
        sma_slow = close.rolling(slow, min_periods=slow).mean()

        diff = (sma_fast - sma_slow) / (close + EPS)
        prox = 1.0 / (1.0 + diff.abs() / (scale + 1e-12))
        prox = prox.replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 1)

        # Rolling log-price slope (vectorised).
        slope = _rolling_log_slope(close, slope_win)
        gate = (slope > 0).astype(float)

        cross_strength = prox * gate
        cross_strength_signed = prox * np.sign(diff).astype(float) * gate
        cross_strength_signed = cross_strength_signed.replace(
            [np.inf, -np.inf], 0
        ).fillna(0)

        diff_filled = diff.fillna(0)
        prev = diff_filled.shift(1).fillna(0)
        cross_up = ((prev <= 0) & (diff_filled > 0)).astype(float)
        cross_down = ((prev >= 0) & (diff_filled < 0)).astype(float)

        return {
            f"sma_fast_{fast}": sma_fast,
            f"sma_slow_{slow}": sma_slow,
            f"sma_diff_{fast}_{slow}": diff,
            f"sma_prox_{fast}_{slow}": prox,
            f"sma_cross_strength_{fast}_{slow}": cross_strength,
            f"sma_cross_strength_signed_{fast}_{slow}": cross_strength_signed,
            f"sma_cross_up_{fast}_{slow}": cross_up,
            f"sma_cross_down_{fast}_{slow}": cross_down,
        }


def _rolling_log_slope(close: pd.Series, window: int) -> pd.Series:
    """Rolling linear-regression slope of log(close) over `window` bars.

    Same idiom as the notebook (lines ~388-399): for each tail window, regress
    log(price) on a centred x-axis and return the slope coefficient.
    """
    if window <= 1:
        return pd.Series(0.0, index=close.index)

    x = np.arange(window, dtype=float)
    x = x - x.mean()
    denom = (x ** 2).sum() + EPS
    logp = np.log(close.astype(float) + EPS)

    def _slope_window(arr: np.ndarray) -> float:
        if len(arr) < window:
            return 0.0
        y = arr[-window:]
        return float(np.dot(y, x) / denom)

    return logp.rolling(window=window, min_periods=window).apply(
        _slope_window, raw=True
    )
