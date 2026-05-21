"""System status, manual-refresh, health, and data-check routes.

PLAN section 8 lists `/api/refresh`, `/api/status`, `/api/data-check`. The
canonical impl uses the `/api/system/*` prefix; thin aliases are provided at
the un-prefixed paths so the Plan's published surface still resolves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd
from fastapi import APIRouter, BackgroundTasks

from backend.config import OHLCV_DIR, TOP200_CURRENT_PATH
from backend.data.data_validator import (
    summarize_validation,
    validate_ohlcv,
    validate_top200,
)
from backend.services.data_service import get_service


router = APIRouter(tags=["system"])


# Phase 3 Module 2: explicit version constant surfaced via /system/status
# so the footer can render it without parsing a Python __version__.
VERSION = "3.0.0"


@router.get("/api/system/status")
def system_status():
    svc = get_service()
    tokens = svc.list_tokens()
    return {
        "status": "ok",
        "version": VERSION,
        "token_count": len(tokens),
        "last_update": svc.last_update,
    }


# Plan-aliased path (PLAN §8: `/api/status`).
@router.get("/api/status")
def system_status_alias():
    return system_status()


@router.get("/api/system/health")
def system_health():
    return {"ok": True}


@router.post("/api/system/refresh")
def system_refresh(background_tasks: BackgroundTasks, full: bool = False):
    """Trigger a background data refresh.

    full=true -> run_full_initial_load (slow!); default is run_daily_update.

    Wired in by main.py to inject the configured Fetcher; if no fetcher is
    available (e.g. unit-test mode), returns status=disabled.
    """
    fetcher = getattr(system_refresh, "_fetcher", None)
    if fetcher is None:
        return {"status": "disabled", "reason": "no fetcher configured"}

    if full:
        background_tasks.add_task(fetcher.run_full_initial_load)
        return {"status": "started", "mode": "full_load"}
    # Phase 3.3 (architect final audit): the user clicks Refresh expecting
    # ALL data to update — both crypto and US stocks. Previously this
    # endpoint only fired run_daily_update (210 crypto tokens); the 38
    # stocks stayed frozen until the 09:05 cron. Queue both jobs in order.
    # FastAPI BackgroundTasks runs added tasks serially in the order they
    # were added, so the second task waits for the first to release the
    # _refresh_lock before acquiring — no skip, no race.
    background_tasks.add_task(fetcher.run_daily_update)
    background_tasks.add_task(fetcher.run_stocks_daily_update)
    return {"status": "started", "mode": "daily_update+stocks"}


# Plan-aliased path (PLAN §8: `/api/refresh`).
@router.post("/api/refresh")
def system_refresh_alias(background_tasks: BackgroundTasks, full: bool = False):
    return system_refresh(background_tasks=background_tasks, full=full)


@router.get("/api/system/refresh-progress")
def refresh_progress():
    """Phase 3.1: live progress of an in-flight run_daily_update /
    run_stocks_daily_update so the frontend can render a real progress
    bar instead of a generic spinner. Returns immediately (single dict
    read from memory, no I/O).

    Response shape:
        phase:        "idle" | "crypto" | "crypto_retry" | "stocks"
        current:      tokens processed so far in the current phase
        total:        total tokens in the current phase
        last_token:   the most-recently processed token id (for UX text)
        started_at:   ISO timestamp of when the current run started
        finished_at:  ISO timestamp of the previous completed run

    When phase == "idle", the UI should hide the progress bar.
    """
    fetcher = getattr(system_refresh, "_fetcher", None)
    if fetcher is None:
        return {"phase": "idle", "current": 0, "total": 0,
                "last_token": None, "started_at": None, "finished_at": None}
    return dict(fetcher._progress)


def bind_fetcher(fetcher) -> None:
    """Inject the fetcher instance for the refresh endpoint."""
    setattr(system_refresh, "_fetcher", fetcher)


# ---------------------------------------------------------------------- #
# Data integrity check (PLAN §8 `/api/data-check`, §11 validation spec).
# ---------------------------------------------------------------------- #
@router.get("/api/data-check")
def data_check(limit: int = 0):
    """Run `validate_ohlcv` over local CSVs and `validate_top200` on the
    universe snapshot. Returns per-token issue lists.

    limit=0 means check every file; positive value caps the scan (useful for
    a quick health probe).
    """
    out: Dict[str, object] = {}

    if Path(TOP200_CURRENT_PATH).exists() and Path(TOP200_CURRENT_PATH).stat().st_size > 0:
        top_df = pd.read_csv(TOP200_CURRENT_PATH)
        out["top200_issues"] = summarize_validation(validate_top200(top_df))
        out["top200_rows"] = int(len(top_df))
    else:
        out["top200_issues"] = "missing top200_current.csv"
        out["top200_rows"] = 0

    per_token: List[Dict] = []
    n_ok = 0
    n_with_issues = 0
    if Path(OHLCV_DIR).exists():
        paths = sorted(Path(OHLCV_DIR).glob("*.csv"))
        if limit and limit > 0:
            paths = paths[: int(limit)]
        for p in paths:
            if p.name.endswith(".tmp"):
                continue
            df = pd.read_csv(p)
            issues = validate_ohlcv(df)
            if issues:
                n_with_issues += 1
                per_token.append({"cg_id": p.stem, "issues": issues, "rows": int(len(df))})
            else:
                n_ok += 1
    out["ohlcv_ok"] = n_ok
    out["ohlcv_with_issues"] = n_with_issues
    out["ohlcv_token_issues"] = per_token
    return out
