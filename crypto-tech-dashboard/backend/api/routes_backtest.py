"""Golden-cross backtest route."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.api._validators import validate_cg_id
from backend.backtest.golden_cross import run_golden_cross_backtest, result_to_dict
from backend.services.data_service import get_service


router = APIRouter(tags=["backtest"])


@router.get("/api/backtest/{cg_id}")
def backtest(
    cg_id: str,
    fast: int = 5,
    slow: int = 20,
    start_date: Optional[str] = None,
):
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    if svc.get_token(cg_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown token {cg_id}")
    df = svc.get_ohlcv(cg_id)
    if df is None or len(df) < (max(fast, slow) + 5):
        raise HTTPException(
            status_code=400,
            detail=f"not enough data for backtest (need >{max(fast, slow)+5} bars)",
        )
    result = run_golden_cross_backtest(
        df, fast=int(fast), slow=int(slow), start_date=start_date
    )
    return {"cg_id": cg_id, "result": result_to_dict(result)}
