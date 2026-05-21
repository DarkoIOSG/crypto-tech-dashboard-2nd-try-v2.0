"""R8-1C: market overview endpoint.

Phase-2 item 5. Surface market-cap, liquidity proxy (24h + 30d volume),
and venue info for each token in one shot.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api._validators import validate_cg_id
from backend.services.data_service import get_service


router = APIRouter(tags=["market"])


@router.get("/api/market_overview/{cg_id}")
def market_overview(cg_id: str):
    """Single-token market info: mcap rank, mcap, 24h vol, 30d avg vol,
    supply numbers, liquidity venue + spot pair, 24h price change."""
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    overview = svc.get_market_overview(cg_id)
    if overview is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown token {cg_id}",
        )
    return overview
