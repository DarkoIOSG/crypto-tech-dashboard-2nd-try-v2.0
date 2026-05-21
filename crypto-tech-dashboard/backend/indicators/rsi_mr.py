"""RSI mean-reversion family — notebook cell 12 lines ~543-565.

Provides explicit oversold-distance soft-features for use as reversal signals.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class RSIMeanReversionFamily(IndicatorFamily):
    name = "rsi_mr"
    default_params = {"period": 14, "rsi_low": 30, "rsi_high": 70, "soft_s": 5.0}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        period = int(p["period"])
        rsi_low = float(p["rsi_low"])
        rsi_high = float(p["rsi_high"])
        soft_s = float(p["soft_s"])

        close = df["close"].astype(float)
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)

        avg_gain = gains.ewm(alpha=1.0 / period, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1.0 / period, adjust=False).mean()
        rs = avg_gain / (avg_loss + EPS)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Soft oversold/overbought activations (sigmoid around the thresholds).
        os_soft = 1.0 / (1.0 + np.exp((rsi - rsi_low) / soft_s))
        ob_soft = 1.0 / (1.0 + np.exp((rsi_high - rsi) / soft_s))

        # Clipped distance (legacy v6.1).
        rsi_dist_os_clip = ((rsi_low - rsi) / rsi_low).clip(lower=0)

        rsi_ma3 = rsi.rolling(3, min_periods=3).mean()
        turn_gap = (rsi - rsi_ma3) / 50.0
        # Mean-reversion soft-turn confirm: oversold * positive turn gap.
        mr_softturn = os_soft * turn_gap.clip(lower=0)

        return {
            f"rsi_mr_dist_os_{period}_clip": rsi_dist_os_clip.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_mr_os_soft_{period}": os_soft.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_mr_ob_soft_{period}": ob_soft.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
            f"rsi_mr_softturn_{period}": mr_softturn.replace(
                [np.inf, -np.inf], 0
            ).fillna(0),
        }
