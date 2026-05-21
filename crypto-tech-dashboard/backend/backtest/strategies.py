"""R8-2B: canonical strategy library — one per indicator family.

Each strategy:
  - reuses backend.indicators.INDICATORS[name].compute(df, **params) so the
    backtest agrees with what the on-screen indicator chart renders
  - returns a position Series ∈ {0, 1} aligned to df.index
  - has a single canonical (entry, exit) rule; the engine handles the rest

Used by:
  - backend.backtest.universe_robustness for the indicator-reliability table
  - future: /api/backtest/{cg_id}?strategy=rsi_oversold_30_50 ad-hoc per-token runs
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

import numpy as np
import pandas as pd

from backend.indicators.registry import INDICATORS


def _first_key_startswith(d: dict, prefix: str):
    """Lookup helper — find the first key in d that starts with `prefix`."""
    for k in d.keys():
        if k.startswith(prefix):
            return d[k]
    return None


def _get_or_prefix(d: dict, exact: str, prefix: str):
    """Like d.get(exact) or first-by-prefix, but pandas-Series-safe.

    The `or` operator triggers Series.__bool__ which raises 'ambiguous
    truth value'. This helper checks for None explicitly.
    """
    v = d.get(exact)
    if v is None:
        v = _first_key_startswith(d, prefix)
    return v


# -----------------------------------------------------------------
# RSI oversold/exit  (long when RSI < entry, flat when RSI > exit)
# -----------------------------------------------------------------
def strategy_rsi_oversold(df: pd.DataFrame, params: dict) -> pd.Series:
    period = int(params.get("period", 14))
    entry = float(params.get("entry", 30))
    exit_thresh = float(params.get("exit", 50))
    series = INDICATORS["rsi"].compute(df, period=period)
    rsi = _get_or_prefix(series, f"rsi_{period}", "rsi_")
    if rsi is None:
        return pd.Series(0, index=df.index)
    sig = pd.Series(0, index=df.index, dtype=int)
    pos = 0
    for i in range(len(df)):
        v = rsi.iloc[i]
        if v != v:        # NaN
            sig.iloc[i] = pos
            continue
        if pos == 0 and v < entry:
            pos = 1
        elif pos == 1 and v > exit_thresh:
            pos = 0
        sig.iloc[i] = pos
    return sig


# -----------------------------------------------------------------
# MACD signal-line cross  (long when MACD > signal)
# -----------------------------------------------------------------
def strategy_macd_signal_cross(df: pd.DataFrame, params: dict) -> pd.Series:
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    signal_w = int(params.get("signal", 9))
    series = INDICATORS["macd"].compute(df, fast=fast, slow=slow, signal=signal_w)
    macd_line = _first_key_startswith(series, "macd_line")
    signal_line = _first_key_startswith(series, "macd_signal")
    if macd_line is None or signal_line is None:
        return pd.Series(0, index=df.index)
    long_mask = (macd_line > signal_line).fillna(False).astype(int)
    return long_mask


# -----------------------------------------------------------------
# KDJ oversold cross  (long when K crosses D up and both < 20)
# -----------------------------------------------------------------
def strategy_kdj_oversold_cross(df: pd.DataFrame, params: dict) -> pd.Series:
    N = int(params.get("N", 9))
    M1 = int(params.get("M1", 3))
    M2 = int(params.get("M2", 3))
    series = INDICATORS["kdj"].compute(df, N=N, M1=M1, M2=M2)
    K = series.get("kdj_k")
    D = series.get("kdj_d")
    if K is None or D is None:
        return pd.Series(0, index=df.index)
    sig = pd.Series(0, index=df.index, dtype=int)
    pos = 0
    for i in range(len(df)):
        k_i = K.iloc[i]; d_i = D.iloc[i]
        if k_i != k_i or d_i != d_i:
            sig.iloc[i] = pos
            continue
        # Entry: K crosses D up while both < 20
        if pos == 0 and i > 0:
            k_prev = K.iloc[i-1]; d_prev = D.iloc[i-1]
            if (k_prev <= d_prev and k_i > d_i and k_i < 20 and d_i < 20):
                pos = 1
        # Exit per Plan Part 3.1: K crosses D DOWN while both > 80
        # (was: k_i > 80 alone — would exit on any overbought reading even
        # without a cross-down confirmation; less symmetric to entry).
        elif pos == 1 and i > 0:
            k_prev = K.iloc[i-1]; d_prev = D.iloc[i-1]
            if (k_prev >= d_prev and k_i < d_i and k_i > 80 and d_i > 80):
                pos = 0
        sig.iloc[i] = pos
    return sig


# -----------------------------------------------------------------
# Bollinger lower-band touch  (long when close < lower band)
# -----------------------------------------------------------------
def strategy_bollinger_lower_band(df: pd.DataFrame, params: dict) -> pd.Series:
    period = int(params.get("period", 20))
    num_std = float(params.get("num_std", 2.0))
    series = INDICATORS["bollinger"].compute(df, period=period, num_std=num_std)
    pctb = _first_key_startswith(series, "bb_pctb")
    if pctb is None:
        return pd.Series(0, index=df.index)
    sig = pd.Series(0, index=df.index, dtype=int)
    pos = 0
    for i in range(len(df)):
        v = pctb.iloc[i]
        if v != v:
            sig.iloc[i] = pos
            continue
        if pos == 0 and v < 0:        # below lower band
            pos = 1
        elif pos == 1 and v > 0.5:    # back to mean
            pos = 0
        sig.iloc[i] = pos
    return sig


# -----------------------------------------------------------------
# SMA golden cross  (fast > slow)
# -----------------------------------------------------------------
def strategy_sma_golden_cross(df: pd.DataFrame, params: dict) -> pd.Series:
    fast = int(params.get("fast", 5))
    slow = int(params.get("slow", 20))
    close = df["close"].astype(float)
    f = close.rolling(fast, min_periods=fast).mean()
    s = close.rolling(slow, min_periods=slow).mean()
    return (f > s).fillna(False).astype(int)


# -----------------------------------------------------------------
# EMA golden cross  (fast > slow)
# -----------------------------------------------------------------
def strategy_ema_golden_cross(df: pd.DataFrame, params: dict) -> pd.Series:
    fast = int(params.get("fast", 5))
    slow = int(params.get("slow", 20))
    close = df["close"].astype(float)
    f = close.ewm(span=fast, adjust=False).mean()
    s = close.ewm(span=slow, adjust=False).mean()
    return (f > s).fillna(False).astype(int)


# -----------------------------------------------------------------
# Momentum breakout  (long when N-day return > threshold)
# -----------------------------------------------------------------
def strategy_momentum_breakout(df: pd.DataFrame, params: dict) -> pd.Series:
    lookback = int(params.get("lookback", 20))
    threshold = float(params.get("threshold", 0.0))
    close = df["close"].astype(float)
    ret = close / close.shift(lookback) - 1.0
    return (ret > threshold).fillna(False).astype(int)


# -----------------------------------------------------------------
# Z-score mean reversion  (long when z < entry_z, exit when z > exit_z)
# -----------------------------------------------------------------
def strategy_zscore_reversion(df: pd.DataFrame, params: dict) -> pd.Series:
    window = int(params.get("window", 40))
    entry_z = float(params.get("entry_z", -2.0))
    exit_z = float(params.get("exit_z", 0.0))
    close = df["close"].astype(float)
    mean = close.rolling(window, min_periods=window).mean()
    std = close.rolling(window, min_periods=window).std()
    z = (close - mean) / (std + 1e-12)
    sig = pd.Series(0, index=df.index, dtype=int)
    pos = 0
    for i in range(len(df)):
        v = z.iloc[i]
        if v != v:
            sig.iloc[i] = pos
            continue
        if pos == 0 and v < entry_z:
            pos = 1
        elif pos == 1 and v > exit_z:
            pos = 0
        sig.iloc[i] = pos
    return sig


# -----------------------------------------------------------------
# Price appreciation breakout
# Plan Part 3.1: entry  20d return > 10% AND vol_z > 2
#               exit   5d return < 0
# (Previously was a duplicate of momentum_breakout — single-bar gate without
# the vol-z confirmation or the 5d-return exit. Audit P1.)
# -----------------------------------------------------------------
def strategy_price_appreciation(df: pd.DataFrame, params: dict) -> pd.Series:
    lookback = int(params.get("lookback", 20))
    threshold = float(params.get("threshold", 0.10))
    vol_z_min = float(params.get("vol_z_min", 2.0))
    exit_window = int(params.get("exit_window", 5))
    close = df["close"].astype(float)
    ret20 = close / close.shift(lookback) - 1.0
    ret5  = close / close.shift(exit_window) - 1.0
    # Volume z-score over its own 20-day rolling mean / std.
    vol = df["volume"].astype(float)
    vol_mean = vol.rolling(lookback).mean()
    vol_std = vol.rolling(lookback).std()
    vol_z = (vol - vol_mean) / vol_std.where(vol_std > 0)

    sig = pd.Series(0, index=df.index, dtype=int)
    pos = 0
    for i in range(len(df)):
        r20 = ret20.iloc[i]; r5 = ret5.iloc[i]; vz = vol_z.iloc[i]
        # Entry: both gates aligned, no NaNs.
        if (pos == 0 and r20 == r20 and vz == vz
                and r20 > threshold and vz > vol_z_min):
            pos = 1
        # Exit: 5d return turned negative.
        elif pos == 1 and r5 == r5 and r5 < 0:
            pos = 0
        sig.iloc[i] = pos
    return sig


CANONICAL_STRATEGIES: Dict[str, Tuple[Callable, dict, str]] = {
    "rsi_oversold_30_50":   (strategy_rsi_oversold,      {"period": 14, "entry": 30, "exit": 50},
                              "RSI Oversold (long RSI<30, exit RSI>50)"),
    "macd_signal_cross":    (strategy_macd_signal_cross, {"fast": 12, "slow": 26, "signal": 9},
                              "MACD Signal Cross (long MACD>signal)"),
    "kdj_oversold_cross":   (strategy_kdj_oversold_cross,{"N": 9, "M1": 3, "M2": 3},
                              "KDJ Oversold Cross (K crosses D up <20)"),
    "bollinger_lower_band": (strategy_bollinger_lower_band,{"period": 20, "num_std": 2.0},
                              "Bollinger Lower Band (long close<lower, exit at mid)"),
    "sma_golden_cross":     (strategy_sma_golden_cross,  {"fast": 5, "slow": 20},
                              "SMA Golden Cross (5/20)"),
    "ema_golden_cross":     (strategy_ema_golden_cross,  {"fast": 5, "slow": 20},
                              "EMA Golden Cross (5/20)"),
    "momentum_breakout":    (strategy_momentum_breakout, {"lookback": 20, "threshold": 0.0},
                              "Momentum Breakout (20d return > 0)"),
    "zscore_reversion":     (strategy_zscore_reversion,  {"window": 40, "entry_z": -2.0, "exit_z": 0.0},
                              "Z-Score Reversion (entry z<-2, exit z>0)"),
    "price_appreciation":   (strategy_price_appreciation,
                              {"lookback": 20, "threshold": 0.10,
                               "vol_z_min": 2.0, "exit_window": 5},
                              "Price Appreciation (20d>10% + vol_z>2; exit 5d<0)"),
}
