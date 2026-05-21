"""MACD family — notebook cell 12 lines ~569-628.

Important: MACD line is **normalised to price** (`/ Close`), not raw EMA diff.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class MACDFamily(IndicatorFamily):
    name = "macd"
    default_params = {"fast": 12, "slow": 26, "signal": 9, "rma_smooth": 3}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        fast = int(p["fast"])
        slow = int(p["slow"])
        signal = int(p["signal"])
        rma_smooth = int(p["rma_smooth"])

        close = df["close"].astype(float)

        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line

        # Price-normalised time series (the notebook uses these for features).
        line_n = (macd_line / (close + EPS)).replace([np.inf, -np.inf], 0).fillna(0)
        signal_n = (signal_line / (close + EPS)).replace([np.inf, -np.inf], 0).fillna(0)
        hist_n = (hist / (close + EPS)).replace([np.inf, -np.inf], 0).fillna(0)

        # RMA-smoothed hist (Wilder smoothing on the histogram).
        hist_rma = (
            hist.ewm(alpha=1.0 / rma_smooth, adjust=False).mean() / (close + EPS)
        )
        hist_rma = hist_rma.replace([np.inf, -np.inf], 0).fillna(0)

        # 5-day hist slope on the price-normalised series.
        hist_slope5 = (hist_n - hist_n.shift(5)) / 5.0
        hist_slope5 = hist_slope5.replace([np.inf, -np.inf], 0).fillna(0)

        # Cross events on normalised hist crossing zero.
        prev = hist_n.shift(1).fillna(0)
        cross_up = ((prev <= 0) & (hist_n > 0)).astype(float)
        cross_down = ((prev >= 0) & (hist_n < 0)).astype(float)
        cross_event = cross_up - cross_down

        key = f"{fast}_{slow}_{signal}"

        return {
            # Raw (un-normalised) — useful for chart rendering.
            "macd_line_raw": macd_line,
            "macd_signal_raw": signal_line,
            "macd_hist_raw": hist,
            # Price-normalised series (used by scoring + ML features).
            f"macd_line_{key}": line_n,
            f"macd_signal_{key}": signal_n,
            f"macd_hist_{key}": hist_n,
            f"macd_hist_rma{rma_smooth}_{key}": hist_rma,
            f"macd_hist_slope5_{key}": hist_slope5,
            f"macd_cross_up_{key}": cross_up,
            f"macd_cross_down_{key}": cross_down,
            f"macd_cross_event_{key}": cross_event,
        }
