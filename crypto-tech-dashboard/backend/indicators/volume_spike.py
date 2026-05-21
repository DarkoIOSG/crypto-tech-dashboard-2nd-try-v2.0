"""Volume-spike family — notebook cell 12 lines ~766-800.

  vol_ratio = volume / volume.rolling(w).mean()
  vol_z     = (volume - mean) / std
  vol_spike_3x      = 1 if vol_ratio >= 3
  vol_spike_2sigma  = 1 if vol_z >= 2
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from backend.indicators.base import EPS, IndicatorFamily, is_close_only, nan_series


class VolumeSpikeFamily(IndicatorFamily):
    name = "volume_spike"
    default_params = {"ma_window": 14}

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        p = self.merged_params(params)
        w = int(p["ma_window"])

        # CoinGecko fallback rows have volume==0 throughout — every output
        # would be 0 and inflate the "no spike" rank for those tokens.
        # Return NaN so cross-sectional ranking treats them as missing.
        if "volume" not in df.columns or is_close_only(df):
            empty = nan_series(df)
            out = {
                f"vol_ma_{w}": empty,
                f"vol_ratio_{w}": empty,
                f"vol_z_{w}": empty,
                f"vol_spike_3x_{w}": empty,
                f"vol_spike_2sigma_{w}": empty,
            }
            # ma_{w} not in the original empty branch but harmless to add.
            return out

        vol = df["volume"].astype(float).fillna(0)

        vol_ma = vol.rolling(w, min_periods=w).mean()
        vol_std = vol.rolling(w, min_periods=w).std()

        vol_ratio = vol / (vol_ma + EPS)
        vol_ratio = vol_ratio.replace([np.inf, -np.inf], 0).fillna(0)

        vol_z = (vol - vol_ma) / (vol_std + EPS)
        vol_z = vol_z.replace([np.inf, -np.inf], 0).fillna(0)

        spike_3x = (vol_ratio >= 3.0).astype(float)
        spike_2sigma = (vol_z >= 2.0).astype(float)

        return {
            f"vol_ma_{w}": vol_ma,
            f"vol_ratio_{w}": vol_ratio,
            f"vol_z_{w}": vol_z,
            f"vol_spike_3x_{w}": spike_3x,
            f"vol_spike_2sigma_{w}": spike_2sigma,
        }
