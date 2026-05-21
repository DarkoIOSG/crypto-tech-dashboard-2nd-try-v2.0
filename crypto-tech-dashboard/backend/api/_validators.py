"""Shared input validators for API routes (P1-B path-traversal hardening).

The cg_id path parameter flows into filesystem paths inside `local_data/ohlcv/`
and `local_data/market_cap/`. A malicious request like
`/api/ohlc/..%2F..%2Fetc%2Fpasswd` (URL-decoded inside FastAPI's router) could
otherwise let `cg_id` reference paths outside the data directory.

CoinGecko coin ids are kebab-case lower-ASCII (see e.g. "bitcoin",
"avalanche-2", "spiko-amundi-overnight-swap-fund-eur"), so a strict regex
allowlist is the right defence. We accept:
    - starts with a-z or 0-9
    - up to 64 chars of [a-z0-9_-]
which matches every cg_id present in our 200-token universe (verified via
`grep -E -v '^[a-z0-9][a-z0-9_-]{0,63}$' on `ls ohlcv/` -> 0 hits).

This module follows the no-try/except hard rule.
"""

from __future__ import annotations

import re

from fastapi import HTTPException


# R8-1D: allow uppercase A-Z and dot for US stock tickers (Phase-2 item 7)
# and future HK-style tickers like `0700.HK`. Still rejects ".." anywhere
# and any leading dot — path-traversal protection intact.
_CG_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-.]{0,63}$")


def validate_cg_id(cg_id: str) -> str:
    """Return `cg_id` if it matches the id allowlist; raise 400 otherwise.

    Accepts CoinGecko ids (lowercase kebab) AND uppercase stock tickers
    (R8-1D). Path-traversal still blocked — leading dot and any ".."
    sequence are rejected explicitly.
    """
    if (
        not isinstance(cg_id, str)
        or not _CG_ID_RE.match(cg_id)
        or cg_id.startswith(".")
        or ".." in cg_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "invalid id; expected ASCII letters / digits / hyphen / "
                "underscore / dot (max 64 chars; no leading dot or '..')"
            ),
        )
    return cg_id
