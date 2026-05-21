"""Token-list / token-detail routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api._validators import validate_cg_id
from backend.services.data_service import get_service


router = APIRouter(tags=["tokens"])


_VALID_ASSET_CLASSES = {"", "crypto", "us-stock"}


@router.get("/api/tokens")
def list_tokens(asset_class: str = ""):
    """R8-1D: optionally filter by asset_class ('crypto' or 'us-stock').
    Empty string returns both classes.

    Phase 3 Module 5: strict validation — typos like 'us_stock' or 'stock'
    now return HTTP 400 instead of silent empty list."""
    if asset_class not in _VALID_ASSET_CLASSES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=(f"invalid asset_class '{asset_class}'; "
                    f"expected one of: 'crypto', 'us-stock', or empty"),
        )
    svc = get_service()
    tokens = svc.list_tokens(asset_class=asset_class or None)
    return {
        "count": len(tokens),
        "asset_class": asset_class or None,
        "tokens": tokens,
    }


@router.get("/api/tokens/{cg_id}")
def get_token(cg_id: str):
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    token = svc.get_token(cg_id)
    if token is None:
        raise HTTPException(status_code=404, detail=f"unknown token {cg_id}")

    # Attach the most-recent close + last-update date if we have OHLCV.
    df = svc.get_ohlcv(cg_id)
    if df is not None and len(df) > 0:
        last_row = df.iloc[-1]
        token["last_close"] = float(last_row["close"])
        token["last_date"] = last_row["date"].strftime("%Y-%m-%d")
        token["ohlcv_rows"] = int(len(df))
        # `source` tag (binance/okx/bybit/gateio/coingecko) — last row.
        token["source"] = str(last_row.get("source") or "")
        # Boolean flag mirroring backend/indicators/base.is_close_only:
        # True iff the *majority* (>=50%) of rows are from coingecko. This
        # matches the indicator-family guard so the badge and the NaN signals
        # are in sync. A token whose last few rows are CG-fallback but whose
        # 3-year history is from a real exchange still has trustworthy
        # H/L/V indicators and is NOT badged.
        src_col = df["source"].astype(str)
        token["close_only_data"] = bool((src_col == "coingecko").mean() >= 0.5)

    return token


# Plan-aliased singular path (PLAN §8: `/api/token/{coin_id}`).
@router.get("/api/token/{cg_id}")
def get_token_alias(cg_id: str):
    cg_id = validate_cg_id(cg_id)
    return get_token(cg_id)


@router.get("/api/ohlc/{cg_id}")
def get_ohlc(cg_id: str, days: int = 0):
    """K-line data for charting.

    days=0 -> all rows; otherwise last N days.
    """
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    rows = svc.get_ohlcv_as_records(cg_id, days=days if days > 0 else None)
    return {"cg_id": cg_id, "count": len(rows), "ohlcv": rows}


@router.get("/api/sparklines")
def get_sparklines(ids: str = "", days: int = 30):
    """P2-3: batch close-only series for the sidebar sparklines.

    `ids` is a comma-separated cg_id list (max 50). Returns
    `{cg_id: [close, ...]}` for each known token; unknown / no-data tokens
    are silently omitted so the frontend can fall through to "no sparkline".
    Each id passes through validate_cg_id (P1-B allowlist regex) so this
    can't be used as a path-traversal vector.
    """
    if not ids:
        return {"count": 0, "sparklines": {}}
    raw_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if len(raw_ids) > 50:
        raw_ids = raw_ids[:50]
    svc = get_service()
    n = max(1, min(int(days), 365))
    out: dict = {}
    for cg_id in raw_ids:
        safe = validate_cg_id(cg_id)
        df = svc.get_ohlcv(safe)
        if df is None or len(df) == 0:
            continue
        tail = df.tail(n)
        out[safe] = [float(v) for v in tail["close"].tolist()]
    return {"count": len(out), "sparklines": out}
