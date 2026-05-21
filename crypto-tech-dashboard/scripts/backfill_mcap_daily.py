"""
backfill_mcap_daily.py — P0-N fix.

Reconstructs the daily market-cap snapshot history (one CSV per UTC day)
that PLAN sec3.2 calls for. Before this script the project had only 2
snapshots in local_data/market_cap/mcap_daily/ (today + yesterday).

Approach:
    1. Load the current Top-N universe from local_data/market_cap/top200_current.csv
       (one row per cg_id, already exclusion-filtered).
    2. For each cg_id, pull `/coins/{id}/market_chart/range` for the last
       N days (default 365). The endpoint returns [timestamp_ms, market_cap]
       sampled multiple times per day. Keep the last sample per UTC day.
    3. Pivot the per-token frames into one daily snapshot per date:
       date -> DataFrame[cg_id, mcap]. Write to mcap_daily/YYYY-MM-DD.csv
       via the local_store's atomic CSV writer.

No try/except outside the existing wrapper carve-out — the CoinGecko
client and LocalStore already absorb all HTTP / FS exceptions. This
module just walks the universe and pipes the dataframes through.

Run via the project venv:
    PYTHONPATH=. ./venv/bin/python scripts/backfill_mcap_daily.py [DAYS]

Pacing:
    CoinGecko Pro tier handles >300 req/min easily; we still pause
    COINGECKO_FALLBACK_DELAY_SECONDS between tokens to keep the per-second
    cap calm.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

# Allow `from backend...` when invoked as a script from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


from backend.config import (
    COINGECKO_FALLBACK_DELAY_SECONDS,
    MCAP_DAILY_DIR,
    PROJECT_ROOT,
    TOP200_CURRENT_PATH,
)
from backend.data.coingecko_client import (
    CoinGeckoClient,
    _request_with_backoff,
    _sleep,
)
from backend.data.local_store import LocalStore


log = logging.getLogger("backfill_mcap_daily")


def _fetch_mcap_history(client: CoinGeckoClient, cg_id: str, days: int) -> pd.DataFrame:
    """Return DataFrame[date (datetime.date), mcap (float)] for `cg_id`.

    Uses /coins/{id}/market_chart/range with `from`/`to` set to (now-days, now).
    Empty DataFrame on failure.
    """
    if not cg_id:
        return pd.DataFrame(columns=["date", "mcap"])

    now = datetime.now(tz=timezone.utc)
    start_dt = now - timedelta(days=int(days) + 2)
    url = f"{client.base_url}/coins/{cg_id}/market_chart/range"
    params = {
        "vs_currency": "usd",
        "from": int(start_dt.timestamp()),
        "to": int(now.timestamp()),
    }
    resp = _request_with_backoff(url, client._headers, params)
    _sleep(COINGECKO_FALLBACK_DELAY_SECONDS)
    if resp is None:
        log.warning("mcap fetch failed: %s", cg_id)
        return pd.DataFrame(columns=["date", "mcap"])

    payload = None
    if resp.status_code < 400:
        # _Resp.json() can raise on malformed JSON; caller-side guard:
        # the helper is small enough that a bare invocation is acceptable.
        # Use the public method but coerce via a no-throw path:
        raw = resp.text or ""
        if not raw.strip():
            return pd.DataFrame(columns=["date", "mcap"])
        import json as _json

        payload = _json.loads(raw)

    if not isinstance(payload, dict):
        return pd.DataFrame(columns=["date", "mcap"])
    mcaps = payload.get("market_caps")
    if not mcaps:
        return pd.DataFrame(columns=["date", "mcap"])

    df = pd.DataFrame(mcaps, columns=["timestamp_ms", "mcap"])
    df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True).dt.date
    # Keep last sample per UTC day (closest to end-of-day mcap).
    df = (
        df.sort_values("timestamp_ms")
        .drop_duplicates(subset="date", keep="last")
        .reset_index(drop=True)
    )
    return df[["date", "mcap"]].copy()


def backfill(days: int = 365) -> Dict[str, int]:
    """Walk top200_current.csv and snapshot mcap_daily for the last `days`.

    Returns a stats dict.
    """
    if not Path(TOP200_CURRENT_PATH).exists():
        log.error("top200_current.csv missing; run a refresh first")
        return {"tokens": 0, "snapshots_written": 0}

    universe = pd.read_csv(TOP200_CURRENT_PATH)
    if "id" not in universe.columns:
        log.error("top200_current.csv missing `id` column")
        return {"tokens": 0, "snapshots_written": 0}

    cg_ids = [str(x) for x in universe["id"].dropna().tolist()]
    log.info("backfill: universe size = %d, days = %d", len(cg_ids), days)

    client = CoinGeckoClient()
    store = LocalStore(Path(PROJECT_ROOT) / "local_data")

    # date -> list of (cg_id, mcap)
    by_date: Dict[str, List[List]] = {}
    n_tokens_with_data = 0

    started = time.time()
    for i, cg_id in enumerate(cg_ids, start=1):
        df = _fetch_mcap_history(client, cg_id, days=days)
        if df.empty:
            continue
        n_tokens_with_data += 1
        for row in df.itertuples(index=False):
            d_iso = row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date)
            by_date.setdefault(d_iso, []).append([cg_id, float(row.mcap)])
        if i % 10 == 0:
            elapsed = time.time() - started
            log.info(
                "progress: %d / %d tokens (%d with data); elapsed=%.1fs",
                i,
                len(cg_ids),
                n_tokens_with_data,
                elapsed,
            )

    # Persist one CSV per date via the store's atomic writer.
    snapshots_written = 0
    for d_iso, rows in sorted(by_date.items()):
        df_snap = pd.DataFrame(rows, columns=["cg_id", "mcap"]).dropna(subset=["cg_id"])
        df_snap = df_snap.drop_duplicates(subset=["cg_id"], keep="last")
        # Coerce to date for the store helper.
        d_date = datetime.fromisoformat(d_iso).date()
        store.write_mcap_snapshot(d_date, df_snap)
        snapshots_written += 1

    log.info(
        "backfill: wrote %d snapshots across %d dates", snapshots_written, len(by_date)
    )
    return {
        "tokens": len(cg_ids),
        "tokens_with_data": n_tokens_with_data,
        "snapshots_written": snapshots_written,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    days = 365
    if len(sys.argv) >= 2 and sys.argv[1].isdigit():
        days = int(sys.argv[1])
    elif len(sys.argv) >= 2:
        log.error("Usage: backfill_mcap_daily.py [DAYS]")
        sys.exit(2)
    stats = backfill(days=days)
    log.info("done: %s", stats)
    n_files = sum(1 for _ in MCAP_DAILY_DIR.glob("*.csv"))
    log.info("mcap_daily/ contains %d CSV files", n_files)


if __name__ == "__main__":
    main()
