"""R8-2A: realized volatility family.

Feeds the Risk sleeve of the Tier-A Overall Score:
    risk_signal_raw = -vol_{w}d            (low vol -> high score)
    risk_signal_cs  = cs_percentile(raw)   (cross-sectionally ranked)

Phase-2 item 2(a). Computed from log returns rolling-std, annualised
to 365 trading days (crypto trades 7×24).
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from backend.indicators.base import IndicatorFamily


class VolatilityFamily(IndicatorFamily):
    name = "volatility"
    default_params = {"windows": [20, 60]}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        windows: List[int] = [int(w) for w in p["windows"]]

        close = df["close"].astype(float)
        # log return for stationarity; rolling std → annualised vol
        log_ret = np.log(close / close.shift(1))
        out: Dict[str, pd.Series] = {}
        for w in windows:
            # min_periods=w to require a full window before emitting; NaN
            # before that pads cleanly through the percentile rank step.
            vol = log_ret.rolling(w, min_periods=w).std() * np.sqrt(365.0)
            vol = vol.replace([np.inf, -np.inf], np.nan)
            out[f"vol_{w}d"] = vol
        return out
