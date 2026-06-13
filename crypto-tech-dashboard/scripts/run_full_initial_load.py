"""Full initial load for GitHub Actions (writes directly to Postgres).

Triggered by: workflow_dispatch with full_load=true on the daily_refresh workflow.
Use this when the Neon database is empty and needs to be seeded with ~6 years
of OHLCV history for all 200 crypto + 40 stock tokens.

Expected runtime on a GitHub Actions ubuntu-latest runner: 15–30 minutes
(API rate limits dominate).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("scripts.run_full_initial_load")


def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        log.error("DATABASE_URL is not set — aborting")
        sys.exit(1)

    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    if not cg_key:
        log.error("COINGECKO_API_KEY is not set — aborting")
        sys.exit(1)

    from backend.db.connection import get_conn, execute_schema
    log.info("Ensuring Postgres schema …")
    conn = get_conn()
    execute_schema(conn)
    conn.close()
    log.info("Schema OK")

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

    log.info("Starting full initial load (crypto + stocks) …")
    fetcher.run_full_initial_load()
    log.info("Full load complete")

    log.info("Running stocks initial load …")
    fetcher.run_stocks_daily_update()
    log.info("Stocks load complete")

    # Sync supporting tables
    _sync_stocks_universe(store)

    # Compute and persist scores snapshot
    from scripts.run_daily_update import _write_scores_snapshot, _sync_stocks_market
    _write_scores_snapshot(store)
    _sync_stocks_market(store)

    log.info("Full initial load finished — database is ready")


def _sync_stocks_universe(store) -> None:
    import pandas as pd
    from backend.config import METADATA_DIR
    path = Path(METADATA_DIR) / "stocks_universe.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    store.write_stocks_universe(df)
    log.info("Synced stocks universe (%d rows)", len(df))


if __name__ == "__main__":
    main()
