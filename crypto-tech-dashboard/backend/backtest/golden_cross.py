"""R8-2B: thin wrapper. Preserves /api/backtest/{cg_id} contract."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from backend.backtest.engine import BacktestResult, result_to_dict, run_backtest
from backend.backtest.strategies import strategy_sma_golden_cross


def run_golden_cross_backtest(df: pd.DataFrame, fast: int = 5, slow: int = 20,
                              start_date: Optional[str] = None) -> BacktestResult:
    return run_backtest(df, strategy=strategy_sma_golden_cross,
                        strategy_params={"fast": int(fast), "slow": int(slow)},
                        start_date=start_date)


__all__ = ["run_golden_cross_backtest", "BacktestResult", "result_to_dict"]
