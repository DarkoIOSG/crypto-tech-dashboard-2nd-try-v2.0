"""R8-2B: generic single-token backtest engine.

Lifted from golden_cross.py and parameterised on a `strategy` callable
that takes an OHLCV DataFrame + a params dict and returns a position
Series ∈ {0, 1} aligned to df.index. Engine handles the rest:
  - one-bar delay between signal and position (next-day execution)
  - commission deduction on transitions (bps × |Δposition|)
  - cumulative equity, CAGR, Sharpe, max DD, win rate, n trades
  - equity-curve sampling for the UI

The golden-cross route (/api/backtest/{cg_id}) still works because
golden_cross.run_golden_cross_backtest is now a thin wrapper around
this engine.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    cagr: float
    sharpe: float
    max_drawdown: float
    n_trades: int
    final_equity: float
    win_rate: float
    avg_trade_return: float           # new in R8-2B
    equity_curve: List[Dict]          # [{date, equity, signal, price}, ...]
    params: Dict


def run_backtest(
    df: pd.DataFrame,
    strategy: Callable[[pd.DataFrame, dict], pd.Series],
    strategy_params: Optional[dict] = None,
    start_date: Optional[str] = None,
    commission_bps: float = 5.0,
) -> BacktestResult:
    """Run one strategy on one token's OHLCV. Returns full stats."""
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)

    if start_date is not None:
        cutoff = pd.to_datetime(start_date)
        work = work[work["date"] >= cutoff].reset_index(drop=True)

    if len(work) < 5:
        return _empty_result(strategy_params or {})

    params = dict(strategy_params or {})
    signal = strategy(work, params)
    if not isinstance(signal, pd.Series):
        signal = pd.Series(signal, index=work.index)
    signal = signal.fillna(0).clip(0, 1).astype(int)
    position = signal.shift(1).fillna(0).astype(int)

    close = work["close"].astype(float)
    ret = close.pct_change().fillna(0.0)
    strat_ret = position * ret

    # Commission deduction on each |Δposition| transition.
    if commission_bps > 0:
        bps_frac = commission_bps / 10_000.0
        trans = position.diff().abs().fillna(0)
        strat_ret = strat_ret - trans * bps_frac

    equity = (1.0 + strat_ret).cumprod()
    days = len(work)
    years = max(days / 365.25, 1.0 / 365.25)
    final_eq = float(equity.iloc[-1]) if len(equity) > 0 else 1.0
    cagr = final_eq ** (1.0 / years) - 1.0 if final_eq > 0 else -1.0

    if strat_ret.std() > 0:
        sharpe = float((strat_ret.mean() / strat_ret.std()) * np.sqrt(365.0))
    else:
        sharpe = 0.0

    running_max = equity.cummax()
    drawdown = (equity / running_max - 1.0)
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    transitions = (position.diff().fillna(0) != 0).sum()
    n_trades = int(transitions)

    # Per-trade returns
    pos_arr = position.values
    rets = ret.values
    in_trade = False
    trade_returns: List[float] = []
    cum = 1.0
    for i in range(len(pos_arr)):
        if pos_arr[i] == 1 and not in_trade:
            in_trade = True
            cum = 1.0
        if in_trade:
            cum *= (1.0 + rets[i])
        if pos_arr[i] == 0 and in_trade:
            in_trade = False
            trade_returns.append(cum - 1.0)
            cum = 1.0
    if in_trade and len(rets) > 0:
        trade_returns.append(cum - 1.0)

    if trade_returns:
        wins = sum(1 for r in trade_returns if r > 0)
        win_rate = float(wins) / float(len(trade_returns))
        avg_trade_return = float(np.mean(trade_returns))
    else:
        win_rate = 0.0
        avg_trade_return = 0.0

    # Equity curve sample
    curve: List[Dict] = []
    sample_idx = range(len(work))
    if len(work) > 1500:
        step = max(1, len(work) // 1000)
        sample_idx = range(0, len(work), step)
    for i in sample_idx:
        curve.append(
            {
                "date": work["date"].iloc[i].strftime("%Y-%m-%d"),
                "equity": float(equity.iloc[i]) if i < len(equity) else 1.0,
                "signal": int(signal.iloc[i]) if i < len(signal) else 0,
                "price": float(close.iloc[i]),
            }
        )

    return BacktestResult(
        cagr=float(cagr),
        sharpe=sharpe,
        max_drawdown=max_dd,
        n_trades=n_trades,
        final_equity=final_eq,
        win_rate=win_rate,
        avg_trade_return=avg_trade_return,
        equity_curve=curve,
        params={**params, "start_date": start_date, "commission_bps": commission_bps},
    )


def _empty_result(params: dict) -> BacktestResult:
    return BacktestResult(
        cagr=0.0, sharpe=0.0, max_drawdown=0.0, n_trades=0,
        final_equity=1.0, win_rate=0.0, avg_trade_return=0.0,
        equity_curve=[], params=dict(params),
    )


def result_to_dict(r: BacktestResult) -> Dict:
    return asdict(r)
