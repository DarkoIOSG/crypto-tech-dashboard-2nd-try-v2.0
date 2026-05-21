"""Z-score vs MA50 family — notebook cell 12 lines ~824-855.

  dev = Close / MA50 - 1
  ma50_dev_z_{w} = (dev - dev.rolling(w).mean()) / dev.rolling(w).std()
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class ZScoreMAFamily(IndicatorFamily):
    name = "zscore_ma"
    default_params = {
        "ma_period": 50,
        "z_windows": [20, 40, 80, 120],
        "slope_windows": [5, 10, 20],
    }

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        ma_period = int(p["ma_period"])
        z_windows: List[int] = list(p["z_windows"])
        slope_windows: List[int] = list(p["slope_windows"])

        close = df["close"].astype(float)
        ma = close.rolling(ma_period, min_periods=ma_period).mean()

        dev = (close / (ma + EPS) - 1.0).replace([np.inf, -np.inf], 0).fillna(0)

        out: Dict[str, pd.Series] = {
            f"ma{ma_period}": ma,
            f"ma{ma_period}_dev": dev,
        }

        for w in z_windows:
            w = int(w)
            mu = dev.rolling(w, min_periods=max(5, w // 4)).mean()
            sd = dev.rolling(w, min_periods=max(5, w // 4)).std()
            z = (dev - mu) / (sd + EPS)
            z = z.replace([np.inf, -np.inf], 0).fillna(0)
            out[f"ma{ma_period}_dev_z_{w}"] = z
            out[f"ma{ma_period}_dev_z_gt2sigma_{w}"] = (z.abs() >= 2.0).astype(float)

        # Cross events (close vs MA).
        prev_close = close.shift(1)
        prev_ma = ma.shift(1)
        cross_up = ((prev_close < prev_ma) & (close > ma)).astype(float)
        cross_dn = ((prev_close > prev_ma) & (close < ma)).astype(float)
        out[f"ma{ma_period}_cross_up"] = cross_up.fillna(0)
        out[f"ma{ma_period}_cross_dn"] = cross_dn.fillna(0)

        # MA slope (rate-of-change of the MA itself).
        for h in slope_windows:
            h = int(h)
            slope = (ma / (ma.shift(h) + EPS) - 1.0).replace(
                [np.inf, -np.inf], 0
            ).fillna(0)
            out[f"ma{ma_period}_slope_{h}d"] = slope

        return out
