"""Scoring routes — current scores + rankings."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from backend.api._validators import validate_cg_id
from backend.services.data_service import get_service


router = APIRouter(tags=["scores"])


_VALID_ASSET_CLASSES = {"", "crypto", "us-stock"}


def _validate_asset_class(asset_class: str) -> str:
    """Phase 3 Module 5: strict asset_class validation. Reject typos / old
    spellings (us_stock, stock) with 400 instead of silent count=0."""
    if asset_class not in _VALID_ASSET_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=(f"invalid asset_class '{asset_class}'; "
                    f"expected one of: 'crypto', 'us-stock', or empty"),
        )
    return asset_class


@router.get("/api/scores")
def all_scores(sort_by: str = "trend", limit: int = 0, asset_class: str = ""):
    """Return scores for every token.

    sort_by:     'trend' or 'reversal' — descending order.
    limit:       if >0, truncate to top N.
    asset_class: 'crypto' or 'us-stock' — filter (R8-1D, Phase-2 item 7).
                 Empty/missing returns both classes mixed; the frontend
                 typically passes one explicitly so cross-class ordering
                 doesn't mislead.
    """
    _validate_asset_class(asset_class)
    svc = get_service()
    scores = svc.current_scores()
    if not scores:
        return {"count": 0, "scores": []}

    token_index: dict = {}
    for t in svc.list_tokens():
        tid = t.get("id")
        if tid:
            token_index[tid] = t

    rows: List[dict] = []
    for cg_id, s in scores.items():
        # R8-1D: filter by asset_class server-side if requested.
        if asset_class and s.get("asset_class") != asset_class:
            continue
        meta = token_index.get(cg_id, {})
        rows.append(
            {
                "cg_id": cg_id,
                "asset_class": s.get("asset_class", "crypto"),
                "symbol": meta.get("symbol") or cg_id.upper(),
                "name": meta.get("name") or cg_id,
                "trend_score": s["trend_score"],
                "reversal_score": s["reversal_score"],
                "trend_cs_percentile": s["trend_cs_percentile"],
                "reversal_cs_percentile": s["reversal_cs_percentile"],
                # R8-2A: Tier-A Overall composite
                "overall_score": s.get("overall_score"),
                "overall_cs_percentile": s.get("overall_cs_percentile"),
                # R8-2C: rank within asset_class universe
                "rank_in_universe_trend": s.get("rank_in_universe_trend"),
                "rank_in_universe_reversal": s.get("rank_in_universe_reversal"),
                "rank_in_universe_overall": s.get("rank_in_universe_overall"),
                "universe_size": s.get("universe_size"),
                "close_only_data": bool(s.get("close_only_data", False)),
            }
        )

    # R8-2A: support sort_by="overall" alongside trend/reversal.
    if sort_by == "reversal":
        key = "reversal_score"
    elif sort_by == "overall":
        key = "overall_score"
    else:
        key = "trend_score"
    rows.sort(key=lambda r: (r.get(key) or 0.0), reverse=True)

    universe_close_only = sum(1 for r in rows if r["close_only_data"])

    if limit and limit > 0:
        rows = rows[: int(limit)]

    return {
        "count": len(rows),
        "sort_by": sort_by,
        "asset_class": asset_class or None,
        "universe_close_only": universe_close_only,
        "scores": rows,
    }


@router.get("/api/scores/{cg_id}/monthly")
def token_score_monthly(cg_id: str):
    """Return monthly overall_score history for one token.

    Response: {"cg_id": str, "months": [{"month": "YYYY-MM", "score": float}]}
    Months are sorted oldest-first. Returns an empty list when the token has
    no scores_history yet.
    """
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    if svc.get_token(cg_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown token {cg_id}")
    months = svc.scores_monthly_for(cg_id)
    return {"cg_id": cg_id, "months": months}


@router.get("/api/scores/{cg_id}")
def token_score(cg_id: str):
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    if svc.get_token(cg_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown token {cg_id}")
    s = svc.score_for(cg_id)
    if s is None:
        # P1-F: mirror P0-I close-only handling. Tokens with <30 OHLCV
        # rows or coingecko-majority source are filtered out of
        # current_scores() because the indicator families return NaN/
        # empty Series. Return 200 with explicit null scores + the
        # same close_only_data / data_insufficient_{2y,3y} flags the
        # frontend already understands from the indicators route, so
        # the UI renders the close-only badge gracefully instead of
        # showing a 404 toast.
        df = svc.get_ohlcv(cg_id)
        close_only = False
        ohlcv_rows = 0
        if df is not None and len(df) > 0:
            ohlcv_rows = int(len(df))
            if "source" in df.columns:
                src_col = df["source"].astype(str)
                close_only = bool((src_col == "coingecko").mean() >= 0.5)
        empty_score = {
            "trend_score": None,
            "reversal_score": None,
            "trend_cs_percentile": None,
            "reversal_cs_percentile": None,
            "trend_components": {},
            "reversal_components": {},
            "trend_ts_2y_percentile": None,
            "reversal_ts_2y_percentile": None,
            "trend_ts_3y_percentile": None,
            "reversal_ts_3y_percentile": None,
            "data_insufficient_2y": True,
            "data_insufficient_3y": True,
            "close_only_data": close_only,
            "ohlcv_rows": ohlcv_rows,
            # R8-2A + R8-2C null surfaces for close-only tokens
            "overall_score": None,
            "overall_cs_percentile": None,
            "overall_components": [],
            "rank_in_universe_trend": None,
            "rank_in_universe_reversal": None,
            "rank_in_universe_overall": None,
            "universe_size": None,
        }
        return {"cg_id": cg_id, "score": empty_score}
    return {"cg_id": cg_id, "score": s}


@router.get("/api/rankings")
def rankings(sort_by: str = "trend", limit: int = 20, asset_class: str = ""):
    """Convenience alias for /api/scores with default limit=20.
    R8-1D: accepts ?asset_class={crypto|us-stock} for sidebar tabs."""
    return all_scores(sort_by=sort_by, limit=limit, asset_class=asset_class)
