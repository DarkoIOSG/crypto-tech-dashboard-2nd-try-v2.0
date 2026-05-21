"""Indicator chart routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from backend.api._validators import validate_cg_id
from backend.indicators.registry import INDICATORS
from backend.services.data_service import get_service


router = APIRouter(tags=["indicators"])


# P2-1: query-string params reserved by the route itself and never passed
# down to a family's compute(**params). Everything else is treated as a
# candidate override, filtered against the family's default_params keys.
_RESERVED_QUERY = {"days"}


def _coerce_param(raw):
    """Coerce a query-string value to int / float / str without exceptions.

    Tries int (with optional leading minus), then float (single decimal
    point), then falls back to the raw string. Empty / None passes through.
    """
    if raw is None or raw == "":
        return raw
    s = str(raw).strip()
    sign = -1 if s.startswith("-") else 1
    digits = s[1:] if s.startswith("-") else s
    if digits.isdigit():
        return sign * int(digits)
    if s.count(".") == 1:
        left, right = s.split(".")
        left_ok = left in ("", "-") or left.lstrip("-").isdigit()
        right_ok = right == "" or right.isdigit()
        if left_ok and right_ok and (left.lstrip("-") + right) != "":
            return float(s)
    return s


def _extract_overrides(request: Request, allowed_keys) -> dict:
    """Pull only those query params whose names match the family's defaults."""
    out: dict = {}
    for key, val in request.query_params.multi_items():
        if key in _RESERVED_QUERY:
            continue
        if key not in allowed_keys:
            continue
        out[key] = _coerce_param(val)
    return out


@router.get("/api/indicators/{cg_id}")
def all_indicators(cg_id: str, days: int = 365):
    """Return all-family chart series for `cg_id`, last `days` bars.

    P0-I: close-only tokens (CoinGecko fallback) and short-history tokens
    (<30 OHLCV bars) used to 404 here because compute_indicators returned
    {}, which broke the frontend's badge/empty-state path. We now return
    200 with empty `series` and a `close_only_data` flag so the UI can
    render the close-only badge and skip the indicator panels gracefully.
    """
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    token = svc.get_token(cg_id)
    if token is None:
        raise HTTPException(status_code=404, detail=f"unknown token {cg_id}")

    series = svc.get_indicators_chart_data(cg_id, days=days if days > 0 else None)
    current = svc.compute_current_indicators(cg_id)

    df = svc.get_ohlcv(cg_id)
    close_only = False
    ohlcv_rows = 0
    if df is not None and len(df) > 0:
        ohlcv_rows = int(len(df))
        if "source" in df.columns:
            src_col = df["source"].astype(str)
            close_only = bool((src_col == "coingecko").mean() >= 0.5)

    return {
        "cg_id": cg_id,
        "days": int(days),
        "series": series,
        "current": current,
        "close_only_data": close_only,
        "ohlcv_rows": ohlcv_rows,
    }


@router.get("/api/indicators/{cg_id}/{family}")
def family_indicators(request: Request, cg_id: str, family: str, days: int = 365):
    """Return just one family's chart series.

    P2-1: accepts arbitrary query-string overrides whose names match the
    family's `default_params` keys (eg. `?fast=5&slow=20` for SMA/EMA/MACD,
    `?period=14` for RSI, `?N=9&M1=3&M2=3` for KDJ). Unknown / reserved
    keys are silently dropped — the frontend never has to know which keys
    a given family understands.
    """
    cg_id = validate_cg_id(cg_id)
    svc = get_service()
    if family not in INDICATORS:
        raise HTTPException(status_code=404, detail=f"unknown family {family}")
    df = svc.get_ohlcv(cg_id)
    if df is None:
        raise HTTPException(
            status_code=404, detail=f"no OHLCV data for {cg_id}"
        )

    fam = INDICATORS[family]
    overrides = _extract_overrides(request, set(fam.default_params.keys()))
    merged = fam.merged_params(overrides)
    produced = fam.compute(df, **overrides)

    if days > 0:
        idx = df.tail(int(days)).index
    else:
        idx = df.index
    date_str = df["date"].dt.strftime("%Y-%m-%d")

    out: dict = {}
    for k, s in produced.items():
        rows = []
        for i in idx:
            v = s.iloc[i] if i < len(s) else None
            fv: Optional[float]
            if v is None:
                fv = None
            else:
                fv = float(v)
                if fv != fv:  # NaN
                    fv = None
            rows.append({"date": date_str.iloc[i], "value": fv})
        out[k] = rows
    return {
        "cg_id": cg_id,
        "family": family,
        "params": merged,
        "defaults": fam.default_params,
        "series": out,
    }
