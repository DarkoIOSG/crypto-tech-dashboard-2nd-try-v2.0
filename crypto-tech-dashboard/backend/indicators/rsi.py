"""RSI family — notebook cell 12 lines ~473-541.

Key formula: Wilder RMA smoothing (alpha = 1/period, adjust=False).
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class RSIFamily(IndicatorFamily):
    name = "rsi"
    default_params = {"period": 14, "rsi_low": 30, "rsi_high": 70}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        period = int(p["period"])
        rsi_low = float(p["rsi_low"])
        rsi_high = float(p["rsi_high"])

        close = df["close"].astype(float)
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)

        avg_gain = gains.ewm(alpha=1.0 / period, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1.0 / period, adjust=False).mean()
        rs = avg_gain / (avg_loss + EPS)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        rsi_scaled = (rsi - 50.0) / 50.0
        rsi_scaled = rsi_scaled.replace([np.inf, -np.inf], 0).fillna(0)

        rsi_dist_os = (rsi_low - rsi) / rsi_low
        rsi_dist_ob = (rsi - rsi_high) / rsi_low

        rsi_dist_os_clip = rsi_dist_os.clip(lower=0)
        rsi_dist_ob_clip = rsi_dist_ob.clip(lower=0)

        # Turning event: RSI crossing its 3-day MA.
        rsi_ma3 = rsi.rolling(window=3, min_periods=3).mean()
        prev_rsi = rsi.shift(1)
        prev_ma = rsi_ma3.shift(1)
        turn_up = ((prev_rsi < prev_ma) & (rsi > rsi_ma3)).astype(float)
        turn_down = ((prev_rsi > prev_ma) & (rsi < rsi_ma3)).astype(float)
        turn_event = turn_up - turn_down

        return {
            f"rsi_{period}": rsi,
            f"rsi_scaled_{period}": rsi_scaled,
            f"rsi_dist_os_{period}": rsi_dist_os.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_dist_ob_{period}": rsi_dist_ob.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_dist_os_{period}_clip": rsi_dist_os_clip.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_dist_ob_{period}_clip": rsi_dist_ob_clip.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_turn_up_{period}": turn_up.fillna(0),
            f"rsi_turn_down_{period}": turn_down.fillna(0),
            f"rsi_turn_event_{period}": turn_event.fillna(0),
        }
