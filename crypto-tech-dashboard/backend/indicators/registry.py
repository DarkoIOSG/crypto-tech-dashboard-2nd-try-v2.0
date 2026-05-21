"""Indicator registry — single source of truth for the 12 families.

Use:
    from backend.indicators.registry import INDICATORS, compute_all
    series_dict = INDICATORS["macd"].compute(df, fast=12, slow=26, signal=9)
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from backend.indicators.base import IndicatorFamily
from backend.indicators.bollinger import BollingerFamily
from backend.indicators.kdj import KDJFamily
from backend.indicators.ma_cross_ema import EMACrossFamily
from backend.indicators.ma_cross_sma import SMACrossFamily
from backend.indicators.macd import MACDFamily
from backend.indicators.mean_reversion import MeanReversionFamily
from backend.indicators.momentum import MomentumFamily
from backend.indicators.price_appreciation import PriceAppreciationFamily
from backend.indicators.rsi import RSIFamily
from backend.indicators.rsi_mr import RSIMeanReversionFamily
from backend.indicators.volatility import VolatilityFamily        # R8-2A
from backend.indicators.volume_spike import VolumeSpikeFamily
from backend.indicators.zscore_ma import ZScoreMAFamily


INDICATORS: Dict[str, IndicatorFamily] = {
    "sma_cross": SMACrossFamily(),
    "ema_cross": EMACrossFamily(),
    "macd": MACDFamily(),
    "rsi": RSIFamily(),
    "rsi_mr": RSIMeanReversionFamily(),
    "kdj": KDJFamily(),
    "bollinger": BollingerFamily(),
    "volume_spike": VolumeSpikeFamily(),
    "momentum": MomentumFamily(),
    "mean_reversion": MeanReversionFamily(),
    "zscore_ma": ZScoreMAFamily(),
    "price_appreciation": PriceAppreciationFamily(),
    # R8-2A: realized vol family — feeds the Risk sleeve of Tier-A Overall.
    # 13th registered family. The frontend's 12-panel grid iterates explicit
    # names so this addition doesn't show up in the chart panels, only in
    # the scoring pipeline.
    "volatility": VolatilityFamily(),
}


def compute_all(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Run every registered family with its default params; flatten into one dict.

    On key collisions across families, later wins — but we have engineered
    family-prefixed keys so this shouldn't happen.
    """
    out: Dict[str, pd.Series] = {}
    for fam_name, fam in INDICATORS.items():
        produced = fam.compute(df)
        for k, v in produced.items():
            out[k] = v
    return out


def compute_family(
    name: str, df: pd.DataFrame, **params
) -> Dict[str, pd.Series]:
    """Compute a single family by registry name.

    Raises KeyError if `name` is unknown — by design (no try/except).
    """
    fam = INDICATORS[name]
    return fam.compute(df, **params)
