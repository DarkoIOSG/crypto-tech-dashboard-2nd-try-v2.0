"""Entry point for the GitHub Actions daily data refresh job.

Wires the Fetcher to a PostgresStore so all writes go to Neon Postgres
instead of local CSV files. After the fetch, computes current scores and
persists the snapshot so the Vercel API can serve /api/scores instantly
without recomputing 240+ indicator sets on cold start.

Required env vars (set as GitHub Actions secrets):
    COINGECKO_API_KEY  — CoinGecko Pro API key
    DATABASE_URL       — Neon Postgres connection string

Optional:
    DATA_DIR           — scratch directory for temp files (default: /tmp/local_data)
                         The Fetcher still resolves symbol_map.json from here;
                         OHLCV writes go to Postgres, not this directory.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the project root (crypto-tech-dashboard/) is on the Python path
# regardless of CWD when the script is invoked.
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("scripts.run_daily_update")


def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        log.error("DATABASE_URL is not set — aborting")
        sys.exit(1)

    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    if not cg_key:
        log.error("COINGECKO_API_KEY is not set — aborting")
        sys.exit(1)

    # --- bootstrap the DB schema (idempotent) ---
    log.info("Ensuring Postgres schema is up to date …")
    from backend.db.connection import get_conn, execute_schema
    conn = get_conn()
    execute_schema(conn)
    conn.close()
    log.info("Schema OK")

    # --- wire fetcher to PostgresStore ---
    from backend.db.postgres_store import PostgresStore
    from backend.data.exchange_client import ExchangeOHLCVClient
    from backend.data.coingecko_client import CoinGeckoClient
    from backend.data.symbol_mapping import SymbolMapper
    from backend.data.fetcher import Fetcher
    from backend.config import METADATA_DIR

    store = PostgresStore()
    exch = ExchangeOHLCVClient()
    cg = CoinGeckoClient()
    mapper = SymbolMapper(METADATA_DIR, exch)

    # DataValidator does CSV-level integrity checks — not applicable to Postgres.
    # Pass a no-op validator so the Fetcher doesn't crash looking for CSV files.
    class _NoOpValidator:
        def validate_ohlcv(self, df, cg_id=""):
            return []
        def validate_top200(self, df):
            return []

    fetcher = Fetcher(
        exchange_client=exch,
        coingecko_client=cg,
        mapper=mapper,
        store=store,
        validator=_NoOpValidator(),
    )

    # --- run crypto daily update ---
    log.info("Starting crypto daily update …")
    fetcher.run_daily_update()
    log.info("Crypto daily update complete")

    # --- run stocks daily update ---
    log.info("Starting US stocks daily update …")
    fetcher.run_stocks_daily_update()
    log.info("Stocks daily update complete")

    # --- sync stocks universe to Postgres (idempotent) ---
    _sync_stocks_universe(store)

    # --- compute and persist scores snapshot ---
    log.info("Computing current scores snapshot …")
    _write_scores_snapshot(store)
    log.info("Scores snapshot persisted")

    log.info("Daily refresh complete — Vercel API is now up to date")


def _sync_stocks_universe(store) -> None:
    """Sync the local stocks_universe.csv to Postgres (idempotent)."""
    import pandas as pd
    from backend.config import METADATA_DIR
    path = Path(METADATA_DIR) / "stocks_universe.csv"
    if not path.exists():
        log.warning("stocks_universe.csv not found at %s — skipping sync", path)
        return
    df = pd.read_csv(path)
    store.write_stocks_universe(df)
    log.info("Synced %d stocks universe rows to Postgres", len(df))


def _write_scores_snapshot(store) -> None:
    """Compute current cross-sectional scores for all tokens and persist them."""
    from backend.services.data_service import DataService, set_service

    # Point DataService at the Postgres-backed store so get_ohlcv() reads from DB.
    svc = DataService()
    svc.refresh_from_disk()   # reads from DB because DATABASE_URL is set
    set_service(svc)

    scores = svc.current_scores()
    if not scores:
        log.warning("No scores computed — snapshot not written")
        return

    store.write_scores_snapshot(scores)
    log.info("Wrote scores snapshot for %d tokens", len(scores))

    # Also persist stocks market overview from yfinance (if available).
    _sync_stocks_market(store)


def _sync_stocks_market(store) -> None:
    """Refresh and persist stocks market data (prices, mcap) to Postgres."""
    import json
    from backend.config import METADATA_DIR
    path = Path(METADATA_DIR) / "stocks_market.json"
    if not path.exists():
        log.info("stocks_market.json not found — skipping sync")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        store._write_metadata("stocks_market", data)
        log.info("Synced stocks_market.json to Postgres (%d tickers)", len(data))
    except Exception as exc:
        log.warning("Failed to sync stocks_market.json: %s", exc)


if __name__ == "__main__":
    main()
