"""Price-appreciation family + volume-event joins — notebook lines ~744-821.

  price_ret_{h}d        = Close / Close.shift(h) - 1
  price_app_5pct_{h}d   = 1 if price_ret_{h}d >= 0.05
  vol3x_and_price5_{w}_{h}d   = vol_spike_3x[w] AND price_app_5pct_{h}d
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily, is_close_only


class PriceAppreciationFamily(IndicatorFamily):
    name = "price_appreciation"
    default_params = {
        "ret_windows": [3, 5, 10, 20],
        "threshold": 0.05,
        "vol_ma_windows": [7, 14, 21],
        "vol_z_windows": [10, 20, 30, 50],
        "vol_spike_3x_thresh": 3.0,
        "vol_spike_2sigma_thresh": 2.0,
    }

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        ret_windows: List[int] = list(p["ret_windows"])
        thresh = float(p["threshold"])
        vol_ma_windows: List[int] = list(p["vol_ma_windows"])
        vol_z_windows: List[int] = list(p["vol_z_windows"])
        spike_3x_t = float(p["vol_spike_3x_thresh"])
        spike_2s_t = float(p["vol_spike_2sigma_thresh"])

        close = df["close"].astype(float)

        out: Dict[str, pd.Series] = {}

        # Price returns and appreciation flags.
        for h in ret_windows:
            h = int(h)
            ret = close / close.shift(h) - 1.0
            ret = ret.replace([np.inf, -np.inf], 0).fillna(0)
            out[f"price_ret_{h}d"] = ret
            out[f"price_app_5pct_{h}d"] = (ret >= thresh).astype(float)

        # Volume joins (only if volume is in df and not the CoinGecko close-
        # only fallback where volume is identically zero). Price-return keys
        # above are close-only-safe, so we keep them; only the volume-join
        # families are skipped.
        if "volume" not in df.columns or is_close_only(df):
            return out

        vol = df["volume"].astype(float).fillna(0)

        # Per-window volume ratios.
        ratios: Dict[int, pd.Series] = {}
        for w in vol_ma_windows:
            w = int(w)
            vma = vol.rolling(w, min_periods=w).mean()
            r = (vol / (vma + EPS)).replace([np.inf, -np.inf], 0).fillna(0)
            ratios[w] = r

        # Per-window volume z-scores.
        zs: Dict[int, pd.Series] = {}
        for w in vol_z_windows:
            w = int(w)
            mu = vol.rolling(w, min_periods=w).mean()
            sd = vol.rolling(w, min_periods=w).std()
            z = ((vol - mu) / (sd + EPS)).replace([np.inf, -np.inf], 0).fillna(0)
            zs[w] = z

        for w, r in ratios.items():
            for h in ret_windows:
                h = int(h)
                ret = out.get(f"price_ret_{h}d")
                if ret is None:
                    continue
                joined = ((r >= spike_3x_t) & (ret >= thresh)).astype(float)
                out[f"vol3x_and_price5_{w}_{h}d"] = joined

        for w, z in zs.items():
            for h in ret_windows:
                h = int(h)
                ret = out.get(f"price_ret_{h}d")
                if ret is None:
                    continue
                joined = ((z >= spike_2s_t) & (ret >= thresh)).astype(float)
                out[f"vol2sigma_and_price5_{w}_{h}d"] = joined

        return out
