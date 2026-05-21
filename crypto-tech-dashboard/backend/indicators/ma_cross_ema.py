"""EMA-crossover family — same structure as SMA family, EWM instead of rolling.

Notebook cell 12, lines ~371-470.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily
from backend.indicators.ma_cross_sma import _rolling_log_slope


class EMACrossFamily(IndicatorFamily):
    name = "ema_cross"
    default_params = {"fast": 5, "slow": 20, "scale": 0.01, "slope_window": 10}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        fast = int(p["fast"])
        slow = int(p["slow"])
        scale = float(p["scale"])
        slope_win = int(p["slope_window"])

        close = df["close"].astype(float)

        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        diff = (ema_fast - ema_slow) / (close + EPS)
        prox = 1.0 / (1.0 + diff.abs() / (scale + 1e-12))
        prox = prox.replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 1)

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
            f"ema_fast_{fast}": ema_fast,
            f"ema_slow_{slow}": ema_slow,
            f"ema_diff_{fast}_{slow}": diff,
            f"ema_prox_{fast}_{slow}": prox,
            f"ema_cross_strength_{fast}_{slow}": cross_strength,
            f"ema_cross_strength_signed_{fast}_{slow}": cross_strength_signed,
            f"ema_cross_up_{fast}_{slow}": cross_up,
            f"ema_cross_down_{fast}_{slow}": cross_down,
        }
