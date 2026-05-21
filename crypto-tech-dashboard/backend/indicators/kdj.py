"""KDJ stochastic family — new, not in notebook. Plan section 4.6.

Standard 9-3-3:
  lowest_low  = Low.rolling(N).min()
  highest_high= High.rolling(N).max()
  RSV         = (Close - lowest_low)/(highest_high - lowest_low + eps) * 100
  K[t]        = (1 - 1/M1)*K[t-1] + (1/M1)*RSV[t]    # init K[0]=50
  D[t]        = (1 - 1/M2)*D[t-1] + (1/M2)*K[t]      # init D[0]=50
  J           = 3*K - 2*D
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily, is_close_only, nan_series


class KDJFamily(IndicatorFamily):
    name = "kdj"
    default_params = {"N": 9, "M1": 3, "M2": 3, "oversold": 20, "overbought": 80}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        N = int(p["N"])
        M1 = int(p["M1"])
        M2 = int(p["M2"])
        oversold = float(p["oversold"])
        overbought = float(p["overbought"])

        # Close-only data (CoinGecko fallback) has degenerate O=H=L=Close —
        # KDJ depends on real High/Low so its output is meaningless. Return
        # NaN for every key so cross-sectional ranking treats this token as
        # missing instead of using poisoned numbers.
        if is_close_only(df):
            empty = nan_series(df)
            return {
                "kdj_k": empty,
                "kdj_d": empty,
                "kdj_j": empty,
                "kdj_os_distance": empty,
                "kdj_ob_distance": empty,
                "kdj_golden_cross": empty,
                "kdj_death_cross": empty,
            }

        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        ll = low.rolling(N, min_periods=N).min()
        hh = high.rolling(N, min_periods=N).max()
        rsv = (close - ll) / ((hh - ll).abs() + EPS) * 100.0
        rsv = rsv.replace([np.inf, -np.inf], np.nan)

        # Iterative K & D — order matters, so a loop is the cleanest expression.
        alpha_k = 1.0 / M1
        alpha_d = 1.0 / M2
        k_arr = np.full(len(close), np.nan, dtype=float)
        d_arr = np.full(len(close), np.nan, dtype=float)
        k_prev = 50.0
        d_prev = 50.0
        rsv_vals = rsv.values
        for i in range(len(close)):
            r = rsv_vals[i]
            if np.isnan(r):
                # Keep prev seeds until RSV is well-defined.
                k_arr[i] = np.nan
                d_arr[i] = np.nan
                continue
            k_now = (1.0 - alpha_k) * k_prev + alpha_k * r
            d_now = (1.0 - alpha_d) * d_prev + alpha_d * k_now
            k_arr[i] = k_now
            d_arr[i] = d_now
            k_prev = k_now
            d_prev = d_now

        K = pd.Series(k_arr, index=close.index)
        D = pd.Series(d_arr, index=close.index)
        J = 3.0 * K - 2.0 * D

        os_distance = (oversold - J) / oversold
        ob_distance = (J - overbought) / oversold

        prev_k = K.shift(1)
        prev_d = D.shift(1)
        golden = ((prev_k < prev_d) & (K > D)).astype(float)
        death = ((prev_k > prev_d) & (K < D)).astype(float)

        return {
            "kdj_k": K,
            "kdj_d": D,
            "kdj_j": J,
            "kdj_os_distance": os_distance.replace([np.inf, -np.inf], 0).fillna(0),
            "kdj_ob_distance": ob_distance.replace([np.inf, -np.inf], 0).fillna(0),
            "kdj_golden_cross": golden.fillna(0),
            "kdj_death_cross": death.fillna(0),
        }
