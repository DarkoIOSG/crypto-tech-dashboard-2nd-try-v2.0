"""R8-2B: indicator robustness endpoints — Phase-2 item 6.

  GET  /api/indicator-robustness                  → aggregate summary
  GET  /api/indicator-robustness/{strategy_name}  → per-token detail
  POST /api/indicator-robustness/recompute        → kick off a fresh run

All three are localhost-friendly. Cache lives in local_data/robustness_cache/
and invalidates when the ohlcv_hash changes (any token CSV mtime/size shifts).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.backtest.universe_robustness import (
    cache_is_fresh,
    read_cache_strategy,
    read_cache_summary,
    run_universe_robustness,
    write_cache,
)
from backend.services.data_service import get_service


log = logging.getLogger(__name__)
router = APIRouter(tags=["robustness"])


_recompute_in_progress = {"flag": False}


def _do_recompute(asset_class: str) -> None:
    """Background-task body — recompute + write cache."""
    if _recompute_in_progress["flag"]:
        log.info("recompute already in progress; skipping")
        return
    _recompute_in_progress["flag"] = True
    try:
        svc = get_service()
        payload = run_universe_robustness(svc, asset_class=asset_class)
        write_cache(payload, asset_class=asset_class)
    finally:
        _recompute_in_progress["flag"] = False


@router.get("/api/indicator-robustness")
def robustness_summary(asset_class: str = "crypto"):
    """Top-level aggregate for the 9 canonical strategies."""
    cached = read_cache_summary(asset_class)
    if cached is None:
        return {
            "available": False,
            "asset_class": asset_class,
            "hint": "no cache; POST /api/indicator-robustness/recompute first",
        }
    fresh = cache_is_fresh(asset_class)
    return {
        "available": True,
        "asset_class": asset_class,
        "cache_fresh": fresh,
        "meta": cached.get("meta"),
        "strategies": cached.get("strategies"),
    }


@router.get("/api/indicator-robustness/{strategy_name}")
def robustness_strategy_detail(strategy_name: str, asset_class: str = "crypto"):
    """Per-token detail for a single strategy."""
    detail = read_cache_strategy(strategy_name, asset_class=asset_class)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"no cache for strategy {strategy_name} (asset_class={asset_class})",
        )
    return {
        "asset_class": asset_class,
        "strategy_name": strategy_name,
        **detail,
    }


@router.post("/api/indicator-robustness/recompute")
def robustness_recompute(background: BackgroundTasks, asset_class: str = "crypto"):
    """Kick off a fresh robustness run. Returns immediately with job id."""
    if _recompute_in_progress["flag"]:
        return {
            "status": "already_in_progress",
            "asset_class": asset_class,
        }
    background.add_task(_do_recompute, asset_class)
    return {
        "status": "started",
        "asset_class": asset_class,
        "hint": "poll /api/indicator-robustness?asset_class=... in ~30-90s",
    }
