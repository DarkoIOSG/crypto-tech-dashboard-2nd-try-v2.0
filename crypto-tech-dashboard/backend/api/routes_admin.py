"""R8-1A: admin routes — single-token repair, boot integrity inspection.

Gated by a localhost-only guard. The dashboard runs at 127.0.0.1:8080 by
default (see scripts/run.sh and the launchd plist), so this is "safe by
default" — only a local user on the same machine can trigger a repair.
If a future deploy exposes the API to a LAN, this guard prevents random
peers from triggering data refetches.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.api._validators import validate_cg_id
from backend.config import DATA_DIR


router = APIRouter(tags=["admin"])


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _require_localhost(request: Request) -> None:
    """Reject any request whose client is not on the loopback interface."""
    client = request.client
    host = (client.host if client is not None else "") or ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(
            status_code=403,
            detail=f"admin endpoint requires loopback access; got client={host}",
        )


@router.post("/api/admin/repair/{cg_id}")
def admin_repair(cg_id: str, request: Request):
    """Re-fetch one token via the full waterfall.

    Use cases:
      - Boot integrity quarantined a token's CSV → repair via the waterfall.
      - An operator notices a token went stale and wants a single-token refresh
        instead of a full daily-update cycle.
    """
    _require_localhost(request)
    cg_id = validate_cg_id(cg_id)
    fetcher = getattr(admin_repair, "_fetcher", None)
    if fetcher is None:
        raise HTTPException(
            status_code=503,
            detail="fetcher not bound at boot — admin actions unavailable",
        )
    summary = fetcher.repair_token(cg_id)
    return summary


@router.get("/api/admin/integrity")
def admin_integrity(request: Request):
    """Return the most recent boot integrity check log.

    Doesn't re-run the check (cheap GET). Reads
    DATA_DIR/metadata/data_integrity_log.json which is written at boot.
    """
    _require_localhost(request)
    log_path = Path(DATA_DIR) / "metadata" / "data_integrity_log.json"
    if not log_path.exists():
        return {"available": False, "reason": "integrity log not yet written"}
    raw = log_path.read_text()
    return {"available": True, "log": json.loads(raw)}


@router.get("/api/data-coverage/{cg_id}")
def data_coverage_one(cg_id: str):
    """R8-1B.2: per-token data quality boundary.

    Returns the slice of local_data/metadata/data_coverage.json for the
    requested token. The frontend uses this to render the "Data Coverage"
    folding row in the score panel (Phase-2 item 11.3 + Q14).
    """
    cg_id = validate_cg_id(cg_id)
    cov_path = Path(DATA_DIR) / "metadata" / "data_coverage.json"
    if not cov_path.exists():
        raise HTTPException(
            status_code=404,
            detail="data_coverage.json not generated yet; run history extension",
        )
    coverage = json.loads(cov_path.read_text() or "{}")
    if cg_id not in coverage:
        raise HTTPException(
            status_code=404,
            detail=f"no coverage record for {cg_id}",
        )
    return {"cg_id": cg_id, "coverage": coverage[cg_id]}


@router.get("/api/data-coverage")
def data_coverage_all():
    """Full coverage map. Reads the whole data_coverage.json file."""
    cov_path = Path(DATA_DIR) / "metadata" / "data_coverage.json"
    if not cov_path.exists():
        return {"count": 0, "coverage": {}}
    coverage = json.loads(cov_path.read_text() or "{}")
    return {"count": len(coverage), "coverage": coverage}


def bind_fetcher(fetcher) -> None:
    """Wire the lifespan-built Fetcher into the admin route handler."""
    admin_repair._fetcher = fetcher
