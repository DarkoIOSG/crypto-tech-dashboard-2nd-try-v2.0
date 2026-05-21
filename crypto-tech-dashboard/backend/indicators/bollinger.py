"""Bollinger Bands family — notebook cell 12 lines ~640-674.

Standard 20-period, 2-sigma. Exposes %B (centred around 0) and width.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class BollingerFamily(IndicatorFamily):
    name = "bollinger"
    default_params = {"period": 20, "num_std": 2.0}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        period = int(p["period"])
        num_std = float(p["num_std"])

        close = df["close"].astype(float)

        mid = close.rolling(period, min_periods=period).mean()
        std = close.rolling(period, min_periods=period).std()
        upper = mid + num_std * std
        lower = mid - num_std * std

        pctb = (close - lower) / ((upper - lower) + EPS) - 0.5
        pctb = pctb.replace([np.inf, -np.inf], 0).fillna(0)

        width = ((upper - lower) / (mid + EPS)).replace([np.inf, -np.inf], 0).fillna(0)

        bb_z = ((close - mid) / (std + EPS)).replace([np.inf, -np.inf], 0).fillna(0)

        return {
            f"bb_mid_{period}": mid,
            f"bb_upper_{period}": upper,
            f"bb_lower_{period}": lower,
            f"bb_pctb_{period}": pctb,
            f"bb_width_{period}": width,
            f"bb_z_{period}": bb_z,
        }
