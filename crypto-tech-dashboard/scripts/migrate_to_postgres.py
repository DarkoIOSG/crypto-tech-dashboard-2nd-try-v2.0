"""One-time migration: copy all existing CSV / JSON data from local_data/
into the Neon Postgres database.

Run this ONCE after setting up the Neon database to seed it with the
historical OHLCV data (248 tokens × ~6 years). After migration, GitHub
Actions takes over for daily incremental updates.

Usage:
    DATABASE_URL="postgresql://..." python scripts/migrate_to_postgres.py

The script is idempotent: existing rows are upserted, not duplicated.
Expected runtime: 2–5 minutes for 248 tokens (~540k rows total).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

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
log = logging.getLogger("scripts.migrate_to_postgres")

import os
import json
import pandas as pd

from backend.db.connection import get_conn, execute_schema
from backend.db.postgres_store import PostgresStore
from backend.config import (
    DATA_DIR,
    MCAP_DIR,
    METADATA_DIR,
    OHLCV_DIR,
)


def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        log.error("DATABASE_URL is not set. Export it before running this script.")
        sys.exit(1)

    # 1. Create / update schema
    log.info("Ensuring schema …")
    conn = get_conn()
    execute_schema(conn)
    conn.close()
    log.info("Schema OK")

    store = PostgresStore()

    # 2. top200_current.csv → tokens table
    _migrate_top200(store)

    # 3. ohlcv/*.csv → ohlcv table
    _migrate_ohlcv(store)

    # 4. scores_history.csv → scores_history table
    _migrate_scores_history(store)

    # 5. last_update.json → metadata
    _migrate_json_file(store, METADATA_DIR / "last_update.json", "last_update")

    # 6. stocks_market.json → metadata
    _migrate_json_file(store, METADATA_DIR / "stocks_market.json", "stocks_market")

    # 7. data_coverage.json → metadata
    _migrate_json_file(store, METADATA_DIR / "data_coverage.json", "data_coverage")

    # 8. stocks_universe.csv → stocks_universe table
    _migrate_stocks_universe(store)

    # 9. Compute and persist scores snapshot
    log.info("Computing current scores snapshot …")
    _write_scores_snapshot(store)

    log.info("Migration complete. The Vercel app is ready to use.")


def _migrate_top200(store: PostgresStore) -> None:
    path = MCAP_DIR / "top200_current.csv"
    if not path.exists():
        log.warning("top200_current.csv not found — skipping")
        return
    df = pd.read_csv(path)
    store.write_top200_current(df)
    log.info("Migrated %d crypto tokens to tokens table", len(df))


def _migrate_ohlcv(store: PostgresStore) -> None:
    if not OHLCV_DIR.exists():
        log.warning("ohlcv/ directory not found — skipping")
        return

    csv_files = sorted(OHLCV_DIR.glob("*.csv"))
    log.info("Migrating %d OHLCV files …", len(csv_files))
    total_rows = 0
    for i, path in enumerate(csv_files, 1):
        cg_id = path.stem
        try:
            df = pd.read_csv(path)
            if df.empty:
                continue
            source = str(df["source"].iloc[-1]) if "source" in df.columns else ""
            store.write_ohlcv(cg_id, df, source)
            total_rows += len(df)
            if i % 25 == 0 or i == len(csv_files):
                log.info("  %d / %d files done (%d rows so far)", i, len(csv_files), total_rows)
        except Exception as exc:
            log.warning("  Skipped %s: %s", cg_id, exc)

    log.info("OHLCV migration complete: %d rows across %d tokens", total_rows, len(csv_files))


def _migrate_scores_history(store: PostgresStore) -> None:
    path = MCAP_DIR / "scores_history.csv"
    if not path.exists():
        log.warning("scores_history.csv not found — skipping")
        return
    df = pd.read_csv(path)
    if df.empty:
        return

    # Group by date and upsert each day.
    dates = df["date"].unique()
    log.info("Migrating scores history: %d dates × %d rows …", len(dates), len(df))
    for date in sorted(dates):
        day_df = df[df["date"] == date].copy()
        store.append_scores_history(date, day_df)
    log.info("Scores history migrated: %d rows", len(df))


def _migrate_json_file(store: PostgresStore, path: Path, key: str) -> None:
    if not path.exists():
        log.info("  %s not found — skipping", path.name)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        store._write_metadata(key, data)
        log.info("Migrated %s → metadata[%s]", path.name, key)
    except Exception as exc:
        log.warning("Failed to migrate %s: %s", path.name, exc)


def _migrate_stocks_universe(store: PostgresStore) -> None:
    path = METADATA_DIR / "stocks_universe.csv"
    if not path.exists():
        log.warning("stocks_universe.csv not found — skipping")
        return
    df = pd.read_csv(path)
    store.write_stocks_universe(df)
    log.info("Migrated %d stocks universe rows", len(df))


def _write_scores_snapshot(store: PostgresStore) -> None:
    from backend.services.data_service import DataService, set_service
    svc = DataService()
    svc.refresh_from_disk()
    set_service(svc)
    scores = svc.current_scores()
    if not scores:
        log.warning("No scores computed — snapshot not written")
        return
    store.write_scores_snapshot(scores)
    log.info("Wrote scores snapshot for %d tokens", len(scores))


if __name__ == "__main__":
    main()
