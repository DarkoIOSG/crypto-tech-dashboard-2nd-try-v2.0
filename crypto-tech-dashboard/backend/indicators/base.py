"""Abstract base class for an indicator family.

Each family computes a small dict of named pandas Series given a daily OHLCV
DataFrame. Families never raise — they trust the input column shape; if a
column is missing this MUST raise loudly (no try/except per hard rules).
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


# Default tiny constant used everywhere to avoid div-by-zero, mirroring the
# notebook (`eps = 1e-8`).
EPS: float = 1e-8


# CoinGecko fallback rows write O=H=L=Close and volume=0 (see
# Fetcher._coingecko_close_to_ohlcv). Indicators that read High / Low / Volume
# would otherwise emit meaningless real numbers and poison the cross-sectional
# ranking. Use the helper below to detect this case and return NaN instead.
def is_close_only(df: pd.DataFrame) -> bool:
    """Return True iff `df` looks like CoinGecko close-only fallback data.

    Detection (any of these is sufficient):
    - The `source` column exists and the dominant (>=50%) value is "coingecko".
    - Volume is identically zero and O==H==L==Close on every row.

    The check is pure (no exceptions). Empty or column-missing dataframes
    return False — those degenerate cases are handled upstream.
    """
    if df is None or len(df) == 0:
        return False
    if "source" in df.columns:
        src = df["source"].astype(str)
        if (src == "coingecko").mean() >= 0.5:
            return True
    needed = ("open", "high", "low", "close", "volume")
    if not all(c in df.columns for c in needed):
        return False
    o = df["open"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    v = df["volume"].astype(float).to_numpy()
    if not np.all(v == 0):
        return False
    # Volumes all zero + O/H/L/Close all coincide (allow tiny float jitter).
    if not np.allclose(o, c, equal_nan=True):
        return False
    if not np.allclose(h, c, equal_nan=True):
        return False
    if not np.allclose(l, c, equal_nan=True):
        return False
    return True


def nan_series(df: pd.DataFrame) -> pd.Series:
    """Return a NaN-filled Series aligned with `df.index` (helper for guards)."""
    return pd.Series([np.nan] * len(df), index=df.index, dtype=float)


class IndicatorFamily:
    """Base contract:

    .name              -> string used in registry keys & API URLs.
    .default_params    -> dict of canonical parameters.
    .compute(df, **kw) -> dict[str, pd.Series] aligned with df.index.

    The base class is intentionally minimal — subclasses override .name,
    .default_params, and .compute().
    """

    name: str = "base"
    default_params: Dict[str, object] = {}

    def merged_params(self, override: Dict[str, object]) -> Dict[str, object]:
        """Merge caller-supplied params over defaults."""
        out = dict(self.default_params)
        if override:
            out.update(override)
        return out

    def compute(self, df: pd.DataFrame, **params) -> Dict[str, pd.Series]:
        raise NotImplementedError
