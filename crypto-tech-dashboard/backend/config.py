"""
backend/config.py
=================

Central configuration for the IOSG Crypto Technical Indicators Dashboard.

Loads environment variables from `.env` (project root) via python-dotenv and
exposes constants used by the data layer (and downstream by indicators / API).

NOTE: This file MUST stay exception-free per the team A1 hard rules.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
# This file lives at: <repo>/crypto-tech-dashboard/backend/config.py
# Project root is two parents up from this file.
BACKEND_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = BACKEND_DIR.parent  # i.e. <repo>/crypto-tech-dashboard

# Load .env from project root (silently does nothing if file is missing).
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


def _env_str(key: str, default: str) -> str:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return value


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    # Strip whitespace; require strictly-numeric to avoid try/except (no exceptions per hard rule).
    cleaned = value.strip()
    if cleaned.startswith("-"):
        digits = cleaned[1:]
        sign = -1
    else:
        digits = cleaned
        sign = 1
    if digits.isdigit():
        return sign * int(digits)
    return default


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# CoinGecko Pro API key. P1-A: NO hardcoded fallback — the key MUST come
# from the .env file (or the process env). When missing/empty here we
# expose it as an empty string and let `CoinGeckoClient.__init__` raise a
# loud, descriptive error on first instantiation. This makes `.env`
# rotation actually work and stops a leaked key from re-entering source.
COINGECKO_API_KEY: str = _env_str("COINGECKO_API_KEY", "")

# Postgres / Neon connection string. When set, DataService reads from Postgres
# and the Fetcher writes to Postgres instead of local CSV files.
# Format: postgresql://user:password@host:port/dbname?sslmode=require
DATABASE_URL: str = _env_str("DATABASE_URL", "")

# Daily-update schedule (consumed by main.py / APScheduler — not by this module).
UPDATE_HOUR: int = _env_int("UPDATE_HOUR", 8)
UPDATE_MINUTE: int = _env_int("UPDATE_MINUTE", 30)
UPDATE_TIMEZONE: str = _env_str("UPDATE_TIMEZONE", "Asia/Shanghai")

# Local data root. If the .env value is relative, resolve against project root.
_data_dir_raw: str = _env_str("DATA_DIR", "./local_data")
_data_dir_path = Path(_data_dir_raw)
if not _data_dir_path.is_absolute():
    DATA_DIR: Path = (PROJECT_ROOT / _data_dir_path).resolve()
else:
    DATA_DIR = _data_dir_path.resolve()

# Universe size and look-back window.
TOP_N: int = _env_int("TOP_N", 200)
HISTORY_DAYS: int = _env_int("HISTORY_DAYS", 1095)

# Exchange priority for the OHLCV waterfall.
# R8-1B.1: extend CCXT from 4 to 8 exchanges to maximise Tier-1 OHLCV
# coverage per Phase-2 plan item 11 + user Q10 ("maximum extraction"). Phase-1
# waterfall had only 4; ~16% of universe fell through to CG close-only.
# Adding Coinbase / Kraken / KuCoin / Bitstamp shrinks the fallback
# footprint without legal risk (all public REST APIs).
EXCHANGE_PRIORITY: list[str] = [
    "binance", "okx", "bybit", "gateio",
    "coinbase", "kraken", "kucoin", "bitstamp",
]

# Source tag used in the CSV `source` column when CoinGecko close-price fallback is used.
COINGECKO_SOURCE_TAG: str = "coingecko"

# Number of ohlcv/ backup directories to keep (P0-M). Each full reload
# snapshots ohlcv/ to ohlcv_backup_YYYYMMDD/ before overwriting; older
# backups beyond this cap are deleted.
BACKUP_KEEP: int = _env_int("BACKUP_KEEP", 3)

# Per-call OHLCV row cap (CCXT honours per-exchange limits internally).
EXCHANGE_OHLCV_LIMIT: int = 1000

# Min number of OHLCV rows required for an exchange result to be considered valid.
MIN_OHLCV_ROWS: int = 30

# CoinGecko pacing.
COINGECKO_PAGE_DELAY_SECONDS: float = 1.5
COINGECKO_FALLBACK_DELAY_SECONDS: float = 1.0
COINGECKO_PER_PAGE: int = 250
COINGECKO_TOTAL_FETCH: int = 750  # 3 pages × 250 (matches notebook cell 2)

# ---------------------------------------------------------------------------
# Directory layout (matches PLAN §2 file tree and §3.2 cache architecture)
# ---------------------------------------------------------------------------

OHLCV_DIR: Path = DATA_DIR / "ohlcv"
MCAP_DIR: Path = DATA_DIR / "market_cap"
MCAP_DAILY_DIR: Path = MCAP_DIR / "mcap_daily"
METADATA_DIR: Path = DATA_DIR / "metadata"

SYMBOL_MAP_PATH: Path = METADATA_DIR / "symbol_map.json"
LAST_UPDATE_PATH: Path = METADATA_DIR / "last_update.json"
DATA_INTEGRITY_LOG_PATH: Path = METADATA_DIR / "data_integrity_log.json"

TOP200_CURRENT_PATH: Path = MCAP_DIR / "top200_current.csv"

# Create the directory tree at import time so downstream code can assume it exists.
# (exist_ok=True is idempotent; no try/except needed.)
for _p in (DATA_DIR, OHLCV_DIR, MCAP_DIR, MCAP_DAILY_DIR, METADATA_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO").upper()
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
if LOG_LEVEL not in _VALID_LOG_LEVELS:
    LOG_LEVEL = "INFO"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("backend.config")
logger.debug(
    "config loaded: DATA_DIR=%s TOP_N=%d HISTORY_DAYS=%d schedule=%02d:%02d %s",
    DATA_DIR,
    TOP_N,
    HISTORY_DAYS,
    UPDATE_HOUR,
    UPDATE_MINUTE,
    UPDATE_TIMEZONE,
)
