-- IOSG Crypto Tech Dashboard — Neon Postgres schema
-- Safe to run repeatedly (all CREATE TABLE IF NOT EXISTS).

-- OHLCV daily bars: one row per (token, date).
-- PRIMARY KEY enforces the dedup that LocalStore did via pandas.
CREATE TABLE IF NOT EXISTS ohlcv (
    cg_id  TEXT            NOT NULL,
    date   DATE            NOT NULL,
    open   DOUBLE PRECISION,
    high   DOUBLE PRECISION,
    low    DOUBLE PRECISION,
    close  DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    source TEXT,
    PRIMARY KEY (cg_id, date)
);

CREATE INDEX IF NOT EXISTS ohlcv_cg_id_date_idx ON ohlcv (cg_id, date DESC);

-- Token universe: top-200 crypto + 40 US stocks.
-- asset_class ∈ {'crypto', 'us-stock'}.
CREATE TABLE IF NOT EXISTS tokens (
    cg_id                       TEXT PRIMARY KEY,
    symbol                      TEXT,
    name                        TEXT,
    asset_class                 TEXT    NOT NULL DEFAULT 'crypto',
    current_price               DOUBLE PRECISION,
    market_cap                  DOUBLE PRECISION,
    market_cap_rank             INTEGER,
    fully_diluted_valuation     DOUBLE PRECISION,
    total_volume                DOUBLE PRECISION,
    circulating_supply          DOUBLE PRECISION,
    total_supply                DOUBLE PRECISION,
    max_supply                  DOUBLE PRECISION,
    price_change_percentage_24h DOUBLE PRECISION,
    active                      BOOLEAN NOT NULL DEFAULT TRUE,
    exchange                    TEXT,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tokens_asset_class_idx ON tokens (asset_class);
CREATE INDEX IF NOT EXISTS tokens_mcap_rank_idx   ON tokens (market_cap_rank);

-- Historical daily scores per token.
-- One row per (token, date); upserted daily by the GitHub Actions job.
CREATE TABLE IF NOT EXISTS scores_history (
    cg_id                  TEXT  NOT NULL,
    date                   DATE  NOT NULL,
    trend_score            DOUBLE PRECISION,
    reversal_score         DOUBLE PRECISION,
    trend_cs_percentile    DOUBLE PRECISION,
    reversal_cs_percentile DOUBLE PRECISION,
    overall_score          DOUBLE PRECISION,
    overall_cs_percentile  DOUBLE PRECISION,
    PRIMARY KEY (cg_id, date)
);

CREATE INDEX IF NOT EXISTS scores_history_cg_id_idx ON scores_history (cg_id, date DESC);

-- Pre-computed current scores snapshot written by the daily job.
-- Allows the API to return /api/scores and /api/rankings without
-- loading all 240+ OHLCV series from Postgres on every cold start.
CREATE TABLE IF NOT EXISTS scores_snapshot (
    cg_id                  TEXT  NOT NULL PRIMARY KEY,
    asset_class            TEXT,
    trend_score            DOUBLE PRECISION,
    reversal_score         DOUBLE PRECISION,
    trend_cs_percentile    DOUBLE PRECISION,
    reversal_cs_percentile DOUBLE PRECISION,
    overall_score          DOUBLE PRECISION,
    overall_cs_percentile  DOUBLE PRECISION,
    rank_in_universe_trend    INTEGER,
    rank_in_universe_reversal INTEGER,
    rank_in_universe_overall  INTEGER,
    universe_size          INTEGER,
    close_only_data        BOOLEAN DEFAULT FALSE,
    trend_components       JSONB,
    reversal_components    JSONB,
    overall_components     JSONB,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Generic key-value metadata store (replaces last_update.json,
-- data_coverage.json, stocks_market.json, etc.).
CREATE TABLE IF NOT EXISTS metadata (
    key        TEXT        PRIMARY KEY,
    value      JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Stocks universe (replaces local_data/metadata/stocks_universe.csv).
CREATE TABLE IF NOT EXISTS stocks_universe (
    ticker   TEXT    PRIMARY KEY,
    name     TEXT,
    exchange TEXT,
    active   BOOLEAN NOT NULL DEFAULT TRUE
);
