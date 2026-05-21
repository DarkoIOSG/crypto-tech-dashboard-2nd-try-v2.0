"""Momentum family — notebook cell 12 lines ~759-764.

  mom_ret_{h}d = Close[t] / Close[t-h] - 1
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from backend.indicators.base import IndicatorFamily


class MomentumFamily(IndicatorFamily):
    name = "momentum"
    default_params = {"windows": [5, 10, 20, 30]}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        windows: List[int] = list(p["windows"])

        close = df["close"].astype(float)
        out: Dict[str, pd.Series] = {}
        for h in windows:
            h = int(h)
            ret = close / close.shift(h) - 1.0
            out[f"mom_ret_{h}d"] = ret.replace([np.inf, -np.inf], 0).fillna(0)
        return out
