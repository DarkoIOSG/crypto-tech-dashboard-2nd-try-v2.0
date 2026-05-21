"""Mean-reversion family — notebook cell 12 lines ~676-739.

Two flavours:
  (A) "MR with skip" (lookback L, skip S):
        ret = P[t-S] / P[t-(L+S)] - 1
        mr  = -ret
        mr_z_{L}_skip{S}   = (mr - mr.mean()) / mr.std()   (rolling)
        mr_rank_{L}_skip{S}= pct rank
  (B) Classic "mean_reversion_{lookback}" = -Z(price) over the lookback window.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily


class MeanReversionFamily(IndicatorFamily):
    name = "mean_reversion"
    default_params = {
        "skip_pairs": [(40, 16), (60, 20)],
        "classic_lookbacks": [20, 60],
        "z_rolling_window": 120,
    }

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        pairs: List[Tuple[int, int]] = [tuple(x) for x in p["skip_pairs"]]
        classics: List[int] = list(p["classic_lookbacks"])
        z_win = int(p["z_rolling_window"])

        close = df["close"].astype(float)
        out: Dict[str, pd.Series] = {}

        # --- Classic mean_reversion_{lookback} = -Z(price)  (notebook lines ~734-739) ---
        for lookback in classics:
            lookback = int(lookback)
            mean_p = close.rolling(lookback, min_periods=lookback).mean()
            std_p = close.rolling(lookback, min_periods=lookback).std()
            z_score = (close - mean_p) / (std_p + EPS)
            mr = -z_score
            out[f"mean_reversion_{lookback}"] = mr.replace(
                [np.inf, -np.inf], 0
            ).fillna(0)

        # --- Skip-MR (notebook lines ~688-729) ---
        for L, S in pairs:
            L = int(L)
            S = int(S)
            px_end = close.shift(S)
            px_start = close.shift(L + S)
            ret = (px_end / (px_start + EPS) - 1.0).replace(
                [np.inf, -np.inf], 0
            ).fillna(0)
            mr = -ret

            mr_mean = mr.rolling(z_win, min_periods=max(20, z_win // 4)).mean()
            mr_std = mr.rolling(z_win, min_periods=max(20, z_win // 4)).std()
            mr_z = (mr - mr_mean) / (mr_std + EPS)
            mr_z = mr_z.replace([np.inf, -np.inf], 0).fillna(0)

            mr_rank = mr.rolling(z_win, min_periods=max(20, z_win // 4)).apply(
                _last_pct_rank, raw=True
            )
            mr_rank = mr_rank.replace([np.inf, -np.inf], 0).fillna(0)

            out[f"mr_skip_ret_{L}_skip{S}"] = ret
            out[f"mr_z_{L}_skip{S}"] = mr_z
            out[f"mr_rank_{L}_skip{S}"] = mr_rank

        return out


def _last_pct_rank(arr: np.ndarray) -> float:
    """Return the percentile rank of the last element within `arr`. 0..1."""
    if arr is None or len(arr) == 0:
        return 0.0
    last = arr[-1]
    if np.isnan(last):
        return 0.0
    # Treat NaN as ignored: count finite values below or equal to last.
    finite = arr[~np.isnan(arr)]
    if len(finite) == 0:
        return 0.0
    return float((finite <= last).sum()) / float(len(finite))
