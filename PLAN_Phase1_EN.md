# Crypto Technical Indicator Analysis Dashboard — Detailed Implementation Plan

> Translated from `PLAN_技术指标Dashboard.md`. This is the Phase-1 implementation plan.

## 1. Project Background and Goals

Convert the existing Jupyter Notebook quantitative technical-indicator analysis workflow into a real-time web application that can be deployed to a Mac server. Users will be able to view the technical-indicator strength, trend/reversal scores, and rankings of the CoinGecko Market Cap Top 200 tokens.

**Key reference file:**
- `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` — covers the data-fetching logic, the token-exclusion logic, and CoinGecko API call patterns. The last cell contains the full `compute_features` indicator source; **all indicator formulas are taken from this last cell as the authoritative source**.

**Final deliverable:** a single-machine Web application deployed on Mac, comprising a backend (Python FastAPI) and a frontend (vanilla JS + TradingView Lightweight Charts). The data is automatically updated daily at 08:30 UTC+8.

---

## 2. Technical Architecture

```
crypto-tech-dashboard/
|-- backend/
|   |-- main.py                       # FastAPI application entry + APScheduler scheduled tasks
|   |-- config.py                     # All constants/configuration (extracted from the notebook)
|   |-- data/
|   |   |-- exchange_client.py        # Unified exchange OHLCV fetcher (CCXT wrapper, Binance→OKX→Bybit→Gate.io waterfall fallback)
|   |   |-- coingecko_client.py       # CoinGecko Pro API wrapper (token list + market cap data)
|   |   |-- symbol_mapping.py         # CoinGecko ID <-> per-exchange trading-pair mapping table
|   |   |-- fetcher.py                # Data-fetching orchestrator (full / incremental / verification)
|   |   |-- exclusion.py              # Token exclusion logic (keyword + ID blacklist)
|   |   |-- local_store.py            # Local file-cache management (CSV read/write, atomic writes)
|   |   |-- data_validator.py         # Data consistency validation (cross-source comparison, date alignment)
|   |-- indicators/
|   |   |-- base.py                   # Abstract base class IndicatorFamily
|   |   |-- ma_cross_sma.py           # SMA cross family
|   |   |-- ma_cross_ema.py           # EMA cross family
|   |   |-- macd.py                   # MACD family
|   |   |-- rsi.py                    # RSI family
|   |   |-- rsi_mr.py                 # RSI mean-reversion family
|   |   |-- kdj.py                    # KDJ stochastic indicator
|   |   |-- bollinger.py              # Bollinger Bands family
|   |   |-- volume_spike.py           # Volume anomaly family
|   |   |-- momentum.py               # Momentum / return family
|   |   |-- mean_reversion.py         # Mean-reversion (skip) family
|   |   |-- zscore_ma.py              # Z-Score vs MA50/MA30 family
|   |   |-- price_appreciation.py     # Price appreciation + joint volume-price events
|   |   |-- registry.py               # Family name -> class registry
|   |-- scoring/
|   |   |-- trend_score.py            # Trend-strength composite score (expanded version)
|   |   |-- reversal_score.py         # Reversal-strength composite score (expanded version)
|   |   |-- ranking.py                # Cross-sectional percentile ranking (2-year / 3-year windows)
|   |-- backtest/
|   |   |-- golden_cross.py           # Simple golden-cross / death-cross backtest
|   |-- api/
|   |   |-- routes_tokens.py          # Token list and details
|   |   |-- routes_indicators.py      # Indicator data and chart data
|   |   |-- routes_scores.py          # Scores and rankings
|   |   |-- routes_backtest.py        # Backtest results
|   |   |-- routes_system.py          # System status, manual refresh, data validation
|-- frontend/
|   |-- index.html                    # Single-page-application shell
|   |-- css/styles.css                # TradingView-style premium dark theme
|   |-- js/
|   |   |-- app.js                    # Main controller
|   |   |-- api.js                    # API client
|   |   |-- charts/                   # Various chart components (candlestick, macd, rsi, etc.)
|   |   |-- components/               # UI components (selector, parameter panel, score card, ranking sidebar)
|   |-- lib/                          # TradingView Lightweight Charts v4
|-- local_data/                       # Local data cache directory
|   |-- ohlcv/                        # OHLCV CSV files per token (uniformly named by CoinGecko ID)
|   |   |-- bitcoin.csv               # Format: date,open,high,low,close,volume,source
|   |   |-- ethereum.csv              #   the `source` column records which exchange the data came from
|   |   |-- ...
|   |-- market_cap/                   # CoinGecko market cap data
|   |   |-- top200_mcap_latest.csv    # Latest Top 200 token list + market caps
|   |   |-- mcap_history.csv          # Historical market-cap data (used for ranking computations)
|   |-- metadata/
|   |   |-- symbol_map.json           # CoinGecko ID <-> Binance symbol mapping
|   |   |-- last_update.json          # Last update timestamp and status
|   |   |-- data_integrity_log.json   # Data validation logs
|-- requirements.txt
|-- run.sh
|-- .env                              # Environment variables (API keys, etc.)
```

**Tech stack:** Python FastAPI + vanilla JS + TradingView Lightweight Charts (open-source, MIT license). Local file caching (CSV), in-memory pandas computation. No Node.js / Webpack build step required.

---

## 3. Data Layer (key chapter)

### 3.1 Data Source Roles and Priority

#### Core principle: keep data sources as unified as possible to avoid cross-source date misalignment; maximize OHLC coverage via multi-exchange waterfall fallback.

| Data type | Primary source | Fallback chain | Notes |
|-----------|----------------|----------------|-------|
| **OHLCV candles** | Exchange public APIs (accessed uniformly via CCXT) | Binance → OKX → Bybit → Gate.io → CoinGecko close price | Each token is fetched from only one exchange to guarantee internal OHLCV consistency |
| **Volume** | Same source as OHLCV (same exchange, same call) | Same as above | Ensures price-volume data are fully co-sourced and co-dated |
| **Close price (for indicator computation)** | Close field from exchange OHLCV | Same as above | Uniformly use exchange Close; do not mix with CoinGecko |
| **Market cap** | CoinGecko Pro API `/coins/markets` | None | Exchanges do not provide market cap; must come from CoinGecko |
| **Token list + ranking** | CoinGecko Pro API `/coins/markets` | None | Provides Top 200 list, current price, and market-cap rank |

#### Multi-exchange OHLCV fetch strategy (unified CCXT layer)

Multiple exchanges are accessed uniformly via the Python CCXT library, with a waterfall fallback in priority order:

| Priority | Exchange | Public API endpoint | Authentication | Rate limit | Symbol format | Max per call |
|----------|----------|--------------------|----|----|----|----|
| 1 | **Binance** | `/api/v3/klines` | None | 6000 weight/min | BTCUSDT | 1000 bars |
| 2 | **OKX** | `/api/v5/market/candles` | None | 20 req/2s | BTC-USDT | 100 bars |
| 3 | **Bybit** | `/v5/market/kline` | None | Lenient | BTCUSDT | 1000 bars |
| 4 | **Gate.io** | `/api/v4/spot/candlesticks` | None | 200 req/10s | BTC_USDT | 1000 bars |
| 5 (last-resort) | **CoinGecko** | `/market_chart/range` | Pro Key | 500 req/min | bitcoin | Close-only |

**Implementation (`exchange_client.py`):**
```python
import ccxt

EXCHANGE_PRIORITY = ['binance', 'okx', 'bybit', 'gateio']

class ExchangeOHLCVClient:
    def __init__(self):
        self.exchanges = {
            'binance': ccxt.binance(),
            'okx': ccxt.okx(),
            'bybit': ccxt.bybit(),
            'gateio': ccxt.gateio(),
        }

    def fetch_ohlcv(self, symbol: str, days: int = 1000) -> tuple[pd.DataFrame, str]:
        """
        Try to fetch OHLCV data from multiple exchanges.
        Returns (DataFrame, name of source exchange).
        """
        for name in EXCHANGE_PRIORITY:
            try:
                # CCXT unified symbol format: "BTC/USDT"
                ohlcv = self.exchanges[name].fetch_ohlcv(
                    symbol, timeframe='1d', limit=days
                )
                if ohlcv and len(ohlcv) > 30:  # at least 30 days of data to be considered valid
                    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
                    df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
                    return df, name
            except Exception:
                continue
        return None, 'none'  # all exchanges failed, fall through to CoinGecko last-resort
```

**Expected coverage uplift:**
- Binance only: ~170/200 tokens (~85%)
- Binance + OKX: ~185/200 tokens (~92%)
- Binance + OKX + Bybit + Gate.io: ~195/200 tokens (~97%)
- The remaining ~5 ultra-niche tokens fall through to CoinGecko (close-only line chart)

#### Why exchange APIs are preferred over CoinGecko for price/volume data

1. **Date-alignment issue**: CoinGecko's `/market_chart/range` may return timestamps that are offset from UTC 00:00 (typically a snapshot taken at some UTC time), whereas exchange klines slice daily strictly on UTC 00:00. Mixing them introduces noise into indicator calculations.
2. **Volume consistency**: CoinGecko volume is the aggregated "total volume" across all exchanges; exchange-API volume is the real volume of that single exchange. OHLCV must be co-sourced to ensure reliable price-volume relationships.
3. **OHLC fidelity**: CoinGecko `/market_chart/range` only returns close prices — no Open/High/Low. Indicators such as KDJ require real High/Low values.

#### Handling of CoinGecko fallback tokens (~5 tokens)

Only tokens that cannot be found on any of the 4 exchanges fall through to CoinGecko:
1. K-line chart: rendered as a close-price line chart (the frontend labels it "close-only data").
2. Technical indicators: Close is available, but KDJ is not available (no High/Low).
3. Scoring: the KDJ sub-signal does not participate in that token's weighting; the other signals are computed normally. In rankings the token is annotated "incomplete data".
4. Expectation: only ~5 ultra-niche tokens reach this stage.

### 3.2 Local File Cache Architecture

#### Why local files rather than a database

- At the bootstrap stage we prioritize debuggability and transparency: CSV files can be opened directly with Excel / pandas for inspection.
- Data volume is small: 200 tokens × 1095 days (3 years) × 6 columns ≈ ~50KB per file, ~10MB total.
- Incremental updates are simple: append one row to the end of the CSV per day.
- Migration to SQLite or Parquet is possible later, but CSV is the most transparent at the initial stage.

#### File structure in detail

```
local_data/
|-- ohlcv/
|   |-- bitcoin.csv          # OHLCV data (source: binance)
|   |-- ethereum.csv         #   format: date,open,high,low,close,volume,source
|   |-- solana.csv           #   date is the UTC date (YYYY-MM-DD)
|   |-- pi-network.csv       #   source column: binance/okx/bybit/gateio/coingecko
|   |-- ...                  #   ~200 files, all named by CoinGecko ID
|
|-- market_cap/
|   |-- top200_current.csv    # current Top 200 list
|   |                         #   format: cg_id,symbol,name,price,mcap,mcap_rank,binance_symbol
|   |-- mcap_daily/           # daily market-cap snapshots (for historical ranking)
|   |   |-- 2024-05-12.csv   #   format: cg_id,mcap
|   |   |-- 2024-05-13.csv
|   |   |-- ...
|
|-- metadata/
|   |-- symbol_map.json       # CoinGecko ID <-> multi-exchange trading-pair mapping
|   |                         #   {"bitcoin":{"exchange":"binance","symbol":"BTC/USDT"},...}
|   |-- last_update.json      # {"last_ohlcv_update":"2026-05-12T08:30:00+08:00",
|   |                         #  "last_mcap_update":"2026-05-12T08:30:00+08:00",
|   |                         #  "status":"idle"|"updating"|"error",
|   |                         #  "error_detail":"..."}
|   |-- data_integrity_log.json  # data-validation result log
```

#### File read/write rules

1. **First start-up (full backfill, may take more than 1 hour and that is acceptable):**
   - Step A: Fetch the CoinGecko Top 200 token list → write to `top200_current.csv`.
   - Step B: Use CCXT to auto-detect symbol mappings across the 4 exchanges → write to `symbol_map.json`.
   - Step C: For each token, in priority order, fetch ~1095 days (3 years) of daily OHLCV from the relevant exchange → write to `ohlcv/{cg_id}.csv`.
   - Step D: For CoinGecko-fallback tokens (~5 of them), call CoinGecko `/market_chart/range` → write to the same directory.
   - Step E: Compute the full historical scores (1095 days × 200 tokens of cross-sectional percentile rankings) → write to `scores_history.csv`.
   - **Fetch-speed estimates**: Binance ~60 seconds (200 tokens, no strict rate-limit); OKX/Bybit/Gate.io fallback tokens 1–3 seconds each; CoinGecko last-resort 1 req/s. Total OHLCV fetch time is roughly 5–10 minutes.
   - **Historical score computation**: 1095 days × 200 tokens × 12 indicator families takes roughly 30–60 minutes. During this time the frontend shows an "Initializing historical data…" progress bar.
   - **Total first-start time is roughly 40–70 minutes**; subsequent restarts load from local files in seconds.
   - To avoid rate-limit issues, CCXT will automatically honour each exchange's `rateLimit` between requests. Additional safety measure: rest 5 seconds after every 50 tokens.

2. **Daily incremental update (triggered at 08:30 UTC+8):**
   - Check the last-row date of each CSV file.
   - If yesterday's data is missing: call the Binance API to fetch the missing days and append to the end of the file.
   - Re-fetch the CoinGecko Top 200 list (the ranking may have changed).
   - Save the day's market-cap snapshot to `mcap_daily/YYYY-MM-DD.csv`.
   - Update `last_update.json`.

3. **Loading data into memory:**
   - At start-up, read all CSV files into pandas DataFrames (merged into wide tables per token).
   - In memory, maintain: `df_prices` (close-price wide table), `df_ohlcv` (dict: cg_id → DataFrame), `df_volume` (volume wide table), `df_mcap` (market-cap wide table), `df_scores_history` (daily score history used for time-series percentiles).
   - After an incremental update: append new rows directly to the in-memory DataFrame; no need to re-read all files.
   - **Score history persistence**: `local_data/scores_history.csv` has the format `date,coin_id,trend_score,reversal_score`. Each daily increment appends 1 day × 200 tokens = 200 rows. This avoids recomputing the full history on restart.

4. **Atomic write protection (data-corruption avoidance):**
   - CSV incremental appends follow a "read original file → append new row → write to a `.tmp` file → `os.rename()` over the original" strategy.
   - `os.rename()` is atomic within the same filesystem; even if the process is killed it will not leave behind half-written files.
   - Before each append, check the last-row date to ensure no duplicate writes.
   - At startup, perform a CSV integrity check: is the last row complete, are dates monotonically increasing, is the column count correct.
   - Record the "list of tokens already updated" in `last_update.json` to support resume-on-failure.

5. **File backup logic:**
   - Before each full backfill, back up the `ohlcv/` directory as `ohlcv_backup_YYYYMMDD/`.
   - Daily incremental updates do not produce a backup (only one row appended, with atomic-write safety).
   - Keep the last 3 backups; older backups are deleted automatically.

### 3.3 Token Filtering Logic

This is a verbatim port of the exclusion logic from cell 2 of the notebook:

**Keyword exclusion (`exclude_keywords`):**
```python
exclude_keywords = [
    "usd", "usdt", "usdc", "busd", "dai", "tusd", "usdp", "gusd", "lusd", "fdusd",
    "usdd", "susd", "eusd", "wrapped", "wbtc", "weth", "renbtc", "staked", "stake"
]
```

**ID blacklist (`exclude_ids`):**
```python
exclude_ids = [
    "bridged-wrapped-ether-starkgate", "sbtc-2", "wrapped-zenbtc", "liquid-hype-yield",
    "compound-ether", "binance-peg-sol", "bitcoin-avalanche-bridged-btc-b", "binance-peg-dogecoin",
    "tbtc", "clbtc", "tether-gold", "rocket-pool-eth", "solv-btc", "pax-gold",
    "cgeth-hashkey", "frax-ether", "resolv-usr", "jupiter-perpetual", "gho",
    "stasis-eurs", "dola-usd", "blockchain-capital",
    "ousg", "mbg-by-multibank-group", "tradable-na-rent-financing-platform-sstn",
    "kinesis-gold", "kinesis-silver", "spiko-us-t-bills-money-market-fund",
    "onyc", "tradable-singapore-fintech-ssl-2", "vaneck-treasury-fund"
]
```

**Exclusion function:**
```python
def is_excluded(coin: dict) -> bool:
    name = coin["name"].lower()
    symbol = coin["symbol"].lower()
    cid = coin["id"].lower()
    return (any(kw in name or kw in symbol for kw in exclude_keywords)
            or cid in exclude_ids)
```

**Flow:** fetch Market Cap Top 250 × 3 pages = 750 tokens → after exclusion, take the first 200.

### 3.4 CoinGecko ID ↔ Exchange Symbol Mapping (multi-exchange)

#### Mapping construction method

1. **CCXT auto-detection**: for each token, use CCXT's `load_markets()` to look up the `{SYMBOL}/USDT` trading pair across the 4 exchanges. CCXT internally maintains the full trading-pair list for each exchange.
2. **Priority selection**: if multiple exchanges list the pair, pick one according to Binance → OKX → Bybit → Gate.io priority.
3. **Manual augmentation**: some tokens have a CoinGecko `symbol` that differs from the exchange symbol (e.g. `polygon-ecosystem-token` corresponds to Binance's `POL/USDT`); maintain a manual override table to handle this.
4. **CoinGecko fallback**: any token not found on any of the 4 exchanges is tagged `exchange: "coingecko"`.

#### Mapping file format (`symbol_map.json`)
```json
{
  "bitcoin": {"exchange": "binance", "symbol": "BTC/USDT", "method": "auto"},
  "ethereum": {"exchange": "binance", "symbol": "ETH/USDT", "method": "auto"},
  "pi-network": {"exchange": "okx", "symbol": "PI/USDT", "method": "auto"},
  "hedera-hashgraph": {"exchange": "binance", "symbol": "HBAR/USDT", "method": "manual"},
  "hashnote-usyc": {"exchange": "coingecko", "symbol": null, "method": "fallback", "reason": "not_on_any_exchange"}
}
```

### 3.5 Data Consistency Validation (key)

#### Issue 1: date alignment between Binance and CoinGecko

- **Binance daily candles**: strictly open at UTC 00:00:00 and close at 23:59:59. The date label is the open time.
- **CoinGecko daily series**: timestamps may be offset (typically near UTC 00:00, but may differ by minutes to hours).
- **Potential misalignment**: CoinGecko's "May 12" data may correspond to Binance's "May 11" or "May 12".

**Validation method:**
```python
# Run automatically at startup: take BTC's most recent 30 days from both sources and compare close prices.
# If CoinGecko[date] ≈ Binance[date].close (error < 0.5%), dates are aligned.
# If CoinGecko[date] ≈ Binance[date-1].close, CoinGecko has a T+1 lag.
# Record the offset in metadata/data_integrity_log.json
```

**Handling plan:**
- If a T+1 lag is detected on CoinGecko market-cap data: automatically shift one day when reading market-cap data.
- Close prices and volume **uniformly use Binance data**, so there is no cross-source alignment problem.
- Market cap is the only quantity that must come from CoinGecko. It is only used for: (a) token-ranking filtering, (b) determining the universe for cross-sectional rankings — both of which have low date-precision requirements (a one-day offset has no impact on Top 200 ranking).

#### Issue 2: Binance volume vs CoinGecko volume

- Binance volume = volume of that trading pair (e.g. BTCUSDT) on Binance alone.
- CoinGecko volume = total volume aggregated across all exchanges.
- The two can differ by 2–10×.

**Handling plan:**
- Indicator computations (VolumeSpike, joint volume-price events) **uniformly use Binance volume**.
- Although Binance is only a single exchange, it is typically one of the largest for the Top 200 tokens.
- Volume-anomaly indicators (`vol_ratio`, `vol_z`) compare a token's volume to its own history (not across tokens), so single-exchange data is acceptable.
- For CoinGecko-fallback tokens (~5), use CoinGecko aggregated volume and annotate the difference in the UI.

#### Issue 3: missing data and anomalies

- **Exchange maintenance / halts**: some tokens may have no trades on some days. Detection: volume = 0 or no row at all that day.
- **Price anomalies**: extreme values from flash crashes/rallies. Detection: intraday amplitude `(high - low) / close > 50%`.
- **Treatment**: mark as anomalous but do not delete. Indicator computations handle anomalous days specially (e.g. skip signal generation for that day).

### 3.6 Update Mechanism in Detail

#### Daily auto-update flow (08:30 UTC+8)

```
08:30:00  Trigger update
          |
          v
Step 1:   Set status = "updating"
          |
          v
Step 2:   Fetch the CoinGecko Top 200 list
          - Check whether new tokens entered / old tokens left
          - For new entries: create OHLCV file, full historical fetch
          - For exits: keep the file but mark inactive
          |
          v
Step 3:   For each token (via CCXT multi-exchange waterfall fallback):
          - Read the last date in the local CSV
          - Through that token's corresponding exchange, fetch the missing days of klines (usually only 1 day)
          - Atomically append to the CSV (.tmp + rename)
          - Append to the in-memory DataFrame
          |
          v
Step 4:   For CoinGecko-fallback tokens (~5):
          - Same logic as above, but call the CoinGecko API (1 req/s rate-limit)
          |
          v
Step 5:   Save the day's market-cap snapshot
          |
          v
Step 6:   Recompute technical indicators for all tokens
          |
          v
Step 7:   Recompute trend / reversal scores and rankings for all tokens
          |
          v
Step 8:   Run data-consistency validation
          |
          v
Step 9:   Set status = "idle"; record update time
```

**Key constraint:** Steps 3–4 run in a background thread; during the update, the frontend API continues to return old data (no blocking). Once the update completes, the system switches to the new data seamlessly.

---

## 4. 12 Technical Indicator Families

All formulas are strictly ported from the `compute_features` method in the last cell of `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb`. KDJ is newly added.

### 6 core families shown by default (visible above the fold)

| # | Family name | Notebook source | Representative chart | Default parameters |
|---|-------------|-----------------|----------------------|--------------------|
| 1 | **SMA cross** | Last cell, lines 196–306 | Price line + SMA fast/slow + golden/death-cross triangle markers | **fast=5**, slow=20 |
| 2 | **MACD** | Last cell, lines 427–495 | Histogram (green up / red down) + MACD line + signal line + zero axis | (12,26,9) |
| 3 | **RSI** | Last cell, lines 331–398 | RSI curve + 30/70 horizontal lines + overbought/oversold shading | period=14 |
| 4 | **Bollinger Bands** | Last cell, lines 497–531 | Price candles + upper/middle/lower bands + band-width fill | period=20, std=2 |
| 5 | **Volume anomaly** | Last cell, lines 599–678 | Volume bars (normal grey / anomaly yellow highlight) + moving average | ma_window=14 |
| 6 | **Momentum** | Last cell, lines 616–621 | Multi-period return lines + zero axis | windows=[5,10,20,30] |

### 6 additional families visible after expanding

| # | Family name | Notebook source | Representative chart | Default parameters |
|---|-------------|-----------------|----------------------|--------------------|
| 7 | **EMA cross** | Last cell, lines 308–328 | Price line + EMA fast/slow + cross markers | fast=5, slow=20 |
| 8 | **RSI mean reversion** | Last cell, lines 400–422 | RSI oversold-distance bar chart (positive = oversold signal strength) | period=14 |
| 9 | **KDJ stochastic** | Newly implemented | K/D/J lines + 20/80 overbought/oversold shading | N=9, M1=3, M2=3 |
| 10 | **Mean reversion (skip)** | Last cell, lines 533–597 | Z-score curve + ±2σ horizontal lines + shading | L=40, S=16 |
| 11 | **Z-Score vs MA50** | Last cell, lines 680–712 | Price + MA50 line + deviation area chart (green above / red below) | ma=50, z_window=40 |
| 12 | **Price appreciation** | Last cell, lines 607–678 | Return bars + joint volume-price event diamond markers | threshold=5% |

### Detailed formulas for each family

#### 4.1 SMA Cross Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 196–306.

**Parameters (user-adjustable):**
- `fast`: fast-line window, default **5**
- `slow`: slow-line window, default 20
- Optional preset combinations: (5,20), (7,30), (10,30), (20,50)

**Computation steps:**
```
1. sma_fast = Close.rolling(fast).mean()
2. sma_slow = Close.rolling(slow).mean()
3. diff = (sma_fast - sma_slow) / Close
4. prox = 1.0 / (1.0 + |diff| / 0.01)          # proximity, 0~1
5. slope_10d = 10-day price slope (linear regression)
6. gate = 1 if slope_10d > 0 else 0              # trend gate
7. cross_strength = prox × gate                   # cross strength (unsigned)
8. cross_strength_signed = prox × sign(diff) × gate  # signed cross strength
9. cross_up = (diff_yesterday ≤ 0) AND (diff_today > 0)  # golden-cross event
10. cross_down = (diff_yesterday ≥ 0) AND (diff_today < 0)  # death-cross event
```

**Output indicators:** `sma_prox`, `sma_cross_strength`, `sma_cross_strength_signed`, `sma_cross_up`, `sma_cross_down`.

**Chart rendering:** price candles/line + SMA fast (blue) + SMA slow (orange) + golden-cross triangle (green-up) + death-cross triangle (red-down).

#### 4.2 EMA Cross Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 308–328.

Identical structure to the SMA family, but uses `ewm(span=w, adjust=False).mean()` instead of `rolling().mean()`.

**Parameters:** fast=5, slow=20 (same as SMA).

**Output indicators:** `ema_prox`, `ema_cross_strength`, `ema_cross_strength_signed`, `ema_cross_up`, `ema_cross_down`.

#### 4.3 MACD Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 427–495.

**Parameters (user-adjustable):**
- `fast`: fast EMA window, default 12
- `slow`: slow EMA window, default 26
- `signal`: signal-line EMA window, default 9
- Optional presets: (5,10,4), (10,20,8), (12,26,9), (20,40,16)

**Computation steps:**
```
1. ema_fast = Close.ewm(span=fast, adjust=False).mean()
2. ema_slow = Close.ewm(span=slow, adjust=False).mean()
3. macd_line = (ema_fast - ema_slow) / Close     # normalized to price
4. signal_line = macd_line.ewm(span=signal, adjust=False).mean()
5. histogram = macd_line - signal_line
6. hist_rma3 = histogram.ewm(alpha=1/3, adjust=False).mean()  # RMA(3) smoothing
7. hist_slope5 = 5-day histogram slope
8. cross_up = (histogram_yesterday ≤ 0) AND (histogram_today > 0)
9. cross_down = (histogram_yesterday ≥ 0) AND (histogram_today < 0)
10. cross_event = cross_up.astype(int) - cross_down.astype(int)  # +1/0/-1
```

**Output indicators:** `macd_line`, `macd_signal`, `macd_hist`, `macd_hist_rma3`, `macd_hist_slope5`, `macd_cross_up`, `macd_cross_down`, `macd_cross_event`.

#### 4.4 RSI Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 331–398.

**Parameters:**
- `period`: RSI window, default 14
- Optional: 7, 14, 21, 28

**Computation steps (Wilder smoothing):**
```
1. delta = Close.diff()
2. gains = delta.clip(lower=0)
3. losses = (-delta).clip(lower=0)
4. avg_gain = gains.ewm(alpha=1.0/period, adjust=False).mean()   # Wilder RMA
5. avg_loss = losses.ewm(alpha=1.0/period, adjust=False).mean()
6. rs = avg_gain / (avg_loss + 1e-10)
7. rsi = 100 - (100 / (1 + rs))
8. rsi_scaled = (rsi - 50) / 50                    # normalized to [-1, 1]
9. rsi_dist_os = (30 - rsi) / 30                   # distance to oversold line (positive = oversold)
10. rsi_dist_ob = (rsi - 70) / 30                  # distance to overbought line (positive = overbought)
11. rsi_dist_os_clip = max(rsi_dist_os, 0)         # keep only the oversold signal
12. rsi_dist_ob_clip = max(rsi_dist_ob, 0)         # keep only the overbought signal
13. rsi_turn_event = RSI's crossover with its 3-day moving average
```

**Output indicators:** `rsi`, `rsi_scaled`, `rsi_dist_os`, `rsi_dist_ob`, `rsi_dist_os_clip`, `rsi_dist_ob_clip`, `rsi_turn_event`.

**Critical note:** Wilder smoothing must be used (`alpha=1/period`), not a simple SMA. This causes minor differences from RSI values produced by some online tools.

#### 4.5 RSI Mean-Reversion Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 400–422.

**Parameters:** period=14 (optional 6, 14, 18, 21, 28).

Uses the distance from the RSI to the oversold line as the mean-reversion signal.

**Output indicators:** `rsi_dist_os_{period}`, `rsi_dist_os_{period}_clip`.

#### 4.6 KDJ Stochastic Indicator (newly added)

**Not present in the original notebook — must be implemented from scratch.**

**Parameters:**
- N=9 (RSV look-back window)
- M1=3 (K-line smoothing factor)
- M2=3 (D-line smoothing factor)

**Computation steps:**
```
1. lowest_low = Low.rolling(N).min()
2. highest_high = High.rolling(N).max()
3. rsv = (Close - lowest_low) / (highest_high - lowest_low + 1e-10) × 100
4. K[0] = 50, D[0] = 50                           # initial values
5. K[t] = (1 - 1/M1) × K[t-1] + (1/M1) × RSV[t]  # i.e. 2/3 × K_prev + 1/3 × RSV
6. D[t] = (1 - 1/M2) × D[t-1] + (1/M2) × K[t]    # i.e. 2/3 × D_prev + 1/3 × K
7. J = 3×K - 2×D
8. kdj_os_distance = (20 - J) / 20                 # distance to oversold zone (positive = oversold)
9. kdj_ob_distance = (J - 80) / 20                 # distance to overbought zone (positive = overbought)
10. kdj_golden_cross = (K_yesterday < D_yesterday) AND (K_today > D_today)  # golden cross
11. kdj_death_cross = (K_yesterday > D_yesterday) AND (K_today < D_today)   # death cross
```

**Note:** KDJ requires High and Low, so it is computed only for tokens that have exchange OHLC data. CoinGecko fallback tokens (close-only, ~5 of them) show N/A for KDJ.

**Output indicators:** `kdj_k`, `kdj_d`, `kdj_j`, `kdj_os_distance`, `kdj_ob_distance`, `kdj_golden_cross`, `kdj_death_cross`.

#### 4.7 Bollinger Bands Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 497–531.

**Parameters:** period=20, num_std=2.0 (optional period: 5, 10, 20, 40, 80).

**Computation steps:**
```
1. mid = Close.rolling(period).mean()              # middle band = SMA
2. std = Close.rolling(period).std()
3. upper = mid + num_std × std                     # upper band
4. lower = mid - num_std × std                     # lower band
5. pctb = (Close - lower) / (upper - lower) - 0.5  # %B, in [-0.5, 0.5]
6. width = (upper - lower) / mid                   # band width
7. bb_z = (Close - mid) / std                      # Z-score
8. squeeze = cross-sectional standardization of -width    # negative = squeeze
```

**Output indicators:** `bb_pctb`, `bb_width`, `bb_z`, `bb_squeeze`, plus `upper`, `mid`, `lower` (for chart overlays).

#### 4.8 Volume Anomaly Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 599–678.

**Parameters:** ma_window=14 (optional 7, 14, 21).

**Computation steps:**
```
1. vol_ma = Volume.rolling(ma_window).mean()
2. vol_std = Volume.rolling(ma_window).std()
3. vol_ratio = Volume / vol_ma                     # volume ratio
4. vol_z = (Volume - vol_ma) / (vol_std + 1e-10)   # volume Z-score
5. vol_spike_3x = (vol_ratio >= 3.0).astype(float)    # 3x-anomaly event
6. vol_spike_2sigma = (vol_z >= 2.0).astype(float)    # 2σ-anomaly event
```

**Output indicators:** `vol_ratio`, `vol_z`, `vol_spike_3x`, `vol_spike_2sigma`.

#### 4.9 Momentum Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 616–621.

**Parameters:** windows=[5,10,20,30].

**Computation:**
```
mom_ret_{h}d = Close / Close.shift(h) - 1          # h-day return
```

**Output indicators:** `mom_ret_5d`, `mom_ret_10d`, `mom_ret_20d`, `mom_ret_30d`.

#### 4.10 Mean-Reversion (skip) Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 533–597.

**Parameters:** L=40 (look-back window), S=16 (skip days).

**Computation:**
```
1. anchor_price = Close.shift(S)                   # price after skipping S days
2. lookback_price = Close.shift(L + S)             # going L days further back
3. ret = anchor_price / lookback_price - 1         # return over that segment
4. mr_z = (ret - ret.rolling(120).mean()) / ret.rolling(120).std()  # Z standardization
5. mr_rank = ret.rank(pct=True)                    # cross-sectional percentile
```

**Output indicators:** `mr_z_{L}_skip{S}`, `mr_rank_{L}_skip{S}`.

#### 4.11 Z-Score vs MA50 Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 680–712.

**Parameters:** ma_period=50, z_windows=[20,40,80,120].

**Computation:**
```
1. ma50 = Close.rolling(50).mean()
2. dev = Close / ma50 - 1                          # relative deviation
3. dev_z_{w} = (dev - dev.rolling(w).mean()) / dev.rolling(w).std()  # Z-score of the deviation
4. dev_z_gt2sigma_{w} = (|dev_z| >= 2).astype(float)  # extreme-deviation event
5. ma50_cross_up = (Close_yesterday < ma50_yesterday) AND (Close_today > ma50_today)
6. ma50_cross_dn = (Close_yesterday > ma50_yesterday) AND (Close_today < ma50_today)
7. ma50_slope_{h}d = (ma50 / ma50.shift(h) - 1)   # h-day change rate of MA50
```

**Output indicators:** `ma50_dev`, `ma50_dev_z_40`, `ma50_dev_z_gt2sigma_40`, `ma50_cross_up`, `ma50_cross_dn`, `ma50_slope_5d`, `ma50_slope_10d`, `ma50_slope_20d`.

#### 4.12 Price Appreciation Family

**Source:** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` last cell, lines 607–678.

**Parameters:** threshold=5%.

**Computation:**
```
1. price_ret_{h}d = Close / Close.shift(h) - 1     # h-day return
2. price_app_5pct_{h}d = (price_ret >= 0.05).astype(float)  # 5%-appreciation event
3. vol3x_and_price5 = vol_spike_3x AND price_app_5pct       # joint volume-price event
4. vol2sigma_and_price5 = vol_spike_2sigma AND price_app_5pct
```

**Output indicators:** `price_ret_20d`, `price_app_5pct_10d`, `vol3x_and_price5_10_10d`, `vol2sigma_and_price5_10_10d`.

---

## 5. Scoring System (expanded version)

### Important notes

1. **About commented-out indicators**: in the last cell of the notebook, some indicators are commented out (e.g. `rsi_turn_event`, `macd_hist_slope5`, `bb_pctb`, labelled "training-window prone to becoming a noise winner"). These are unstable inside an ML-driven automatic feature-selection framework, but they remain valid in the Dashboard's fixed scoring system — the Dashboard does not perform ML feature selection, but instead uses a fixed set of pre-defined signals for scoring, so these indicators are still included.

2. **Parameter selection**: the scores use **one set of default parameters per family** (e.g. MACD only uses 12,26,9; SMA cross only uses 5,20). No multi-parameter automatic selection is performed. The frontend charts default to the same parameter set, but the user can adjust them manually (adjustments affect only the chart, not the scores).

### 5.1 Trend-Strength Score (0–100)

Measures the strength of a bullish trend. Combines signals from several indicator families, ranking by cross-sectional percentile and taking an equal-weight average.

#### Trend-score components (expanded to 9 signals)

| Group | Signal name | Indicator | Meaning | Weight |
|-------|-------------|-----------|---------|--------|
| **Momentum** | Short-term momentum | `mom_ret_10d` | 10-day return | 1 |
| **Momentum** | Mid-term momentum | `mom_ret_20d` | 20-day return | 1 |
| **MACD** | MACD histogram | `macd_hist_12_26_9` | Positive = bullish | 1 |
| **MACD** | MACD histogram slope | `macd_hist_slope5_12_26_9` | Positive slope = building momentum | 1 |
| **SMA cross** | SMA golden-cross strength | `sma_cross_strength_signed_5_20` | Positive = fast above slow | 1 |
| **EMA cross** | EMA golden-cross strength | `ema_cross_strength_signed_5_20` | Positive = fast above slow (more sensitive) | 1 |
| **Z-Score MA50** | MA50 trend slope | `ma50_slope_20d` | Positive slope = MA50 rising | 1 |
| **Z-Score MA50** | MA50 deviation | `ma50_dev` | Positive deviation = price above MA50 | 1 |
| **Bollinger** | Bollinger position | `bb_pctb_20` | Close to upper band = strong | 1 |

**Computation:**
```python
def trend_strength(all_tokens_indicators: dict) -> dict:
    signals = [
        'mom_ret_10d', 'mom_ret_20d',
        'macd_hist_12_26_9', 'macd_hist_slope5_12_26_9',
        'sma_cross_strength_signed_5_20', 'ema_cross_strength_signed_5_20',
        'ma50_slope_20d', 'ma50_dev', 'bb_pctb_20'
    ]
    # For each signal, compute the cross-sectional percentile rank (0~100) across all 200 tokens
    percentiles = {}
    for sig in signals:
        values = {token: indicators[sig] for token, indicators in all_tokens_indicators.items()}
        series = pd.Series(values)
        percentiles[sig] = series.rank(pct=True) * 100

    # Equal-weight average of the percentiles of all signals
    trend_scores = sum(percentiles[sig] for sig in signals) / len(signals)
    return trend_scores  # Series: token -> score (0-100)
```

### 5.2 Reversal-Strength Score (0–100)

Measures oversold / reversal potential. Combines signals from oversold-style indicators.

#### Reversal-score components (expanded to 7 signals)

| Group | Signal name | Indicator | Meaning | Weight |
|-------|-------------|-----------|---------|--------|
| **RSI** | RSI oversold distance | `rsi_dist_os_14` | Positive = more oversold | 1 |
| **RSI** | RSI reversal event | `rsi_turn_event_14` | RSI turns up from oversold zone | 1 |
| **KDJ** | KDJ oversold distance | `kdj_os_distance` | J-line below 20 = oversold | 1 |
| **Bollinger** | Bollinger Z-Score (inverted) | `-bb_z_20` | Below the lower band = oversold | 1 |
| **Mean reversion** | MR Z-Score | `mr_z_40_skip16` | High value = strong mean-reversion signal | 1 |
| **Z-Score MA50** | MA50 deviation (inverted) | `-ma50_dev_z_40` | Far below MA50 = reversal potential | 1 |
| **Momentum** | Short-term negative momentum | `-mom_ret_5d` | Large recent drop = oversold | 1 |

**Computation:** same as trend strength — cross-sectional percentile ranking followed by equal-weight average.

### 5.3 Percentile-Ranking Mechanism (2-year / 3-year windows)

#### Core requirement

In addition to cross-sectional ranking across the current Top 200 tokens, the system must provide a **time-series-dimension** percentile — i.e. where the token's current trend / reversal score sits within its own history over the last 2 or 3 years.

#### Two ranking dimensions

| Ranking dimension | Meaning | Computation |
|-------------------|---------|-------------|
| **Cross-sectional rank** | The token's position right now within the 200 tokens | `score.rank(pct=True) * 100`, a single number |
| **Time-series rank (2-year)** | The token's current score's position within its own past-2-year scores | Take the last 730 days (2 trading years) of daily scores; compute the current value's percentile |
| **Time-series rank (3-year)** | The token's current score's position within its own past-3-year scores | Same with the last 1095 days |

#### Implementation

```python
def time_series_percentile(current_score: float, historical_scores: pd.Series, years: int) -> float:
    """
    Compute the percentile of current_score within historical_scores over the past N years.
    """
    cutoff = len(historical_scores) - years * 365
    recent = historical_scores.iloc[max(0, cutoff):]
    return (recent < current_score).mean() * 100
```

#### Display

```
Trend strength: 72 / 100
├── Cross-sectional rank: Top 15%  (within the current 200 tokens)
├── 2-year historical rank: Top 22% (within BTC's own past 2 years)
└── 3-year historical rank: Top 18% (within BTC's own past 3 years)
```

This lets the user see at the same time: (a) how strong this token is in the current market, and (b) how strong this token is within its own history.

---

## 6. Backtest Module (additional feature)

- **Strategy:** SMA(fast) crosses up through SMA(slow) = golden-cross buy (next-day close); crosses down = death-cross sell.
- **Output metrics:** cumulative-return curve, total return, annualized return, Sharpe ratio, max drawdown, win rate, number of trades.
- **User-adjustable parameters:** fast/slow windows (default 5/20), backtest start date.
- **Display location:** collapsible panel at the bottom of the main page.

---

## 7. Frontend Page Design

### 7.1 Overall Layout

Desktop-first design with basic mobile adaptation (single-column layout, charts adapt their width).

```
+------------------------------------------------------------------+--------+
| Top bar: "Crypto Tech Dashboard"     last updated | [Refresh]    | Ranking|
+------------------------------------------------------------------+ sidebar|
| [BTC v] Token selector (searchable)   $104,230   Mcap: $2.03T   | (col-  |
| Trend: 72 (Cross-sec Top 15% | 2y Top 22%)                      | lapsi- |
| Reversal: 34 (Cross-sec Top 78% | 2y Top 65%)                   | ble)   |
+------------------------------------------------------------------+        |
| Main K-line chart (candles + volume bars, ~35% height)            | Top 20 |
| Real Binance OHLC candle data                                     | tokens |
| TradingView Lightweight Charts, zoom/drag supported               | sorted |
+------------------------------------------------------------------+ by     |
| 6 core indicator panels (2-column grid)                           | trend  |
| +---------------------------+  +---------------------------+      | or     |
| | SMA cross (5/20)          |  | MACD (12,26,9)            |      | reversal|
| | [fast: 5] [slow: 20]      |  | [fast: 12] [slow: 26]     |      |        |
| | <price + dual MA + golden/death-cross markers>            |      | Click  |
| +---------------------------+  +---------------------------+      | to     |
| | RSI (14)                  |  | Bollinger (20)            |      | switch |
| | [period: 14]              |  | [period: 20] [std: 2]     |      | main   |
| | <RSI line + 30/70 + shading>  | <candles + 3 bands + fill>|     | view   |
| +---------------------------+  +---------------------------+      |        |
| | Volume anomaly (14)       |  | Momentum                  |      |        |
| | [window: 14]              |  | [5d/10d/20d/30d]          |      |        |
| | <volume bars + anomaly yellow highlight> | <multi-line + zero>|  |        |
| +---------------------------+  +---------------------------+      |        |
|                                                                   |        |
| [▼ Show more indicators]                                          |        |
| +---------------------------+  +---------------------------+      |        |
| | EMA cross (5/20)          |  | RSI mean-reversion (14)   |      |        |
| +---------------------------+  +---------------------------+      |        |
| | KDJ (9,3,3)               |  | Mean reversion skip (40,16)|     |        |
| +---------------------------+  +---------------------------+      |        |
| | Z-Score vs MA50           |  | Price appreciation        |      |        |
| +---------------------------+  +---------------------------+      |        |
+------------------------------------------------------------------+        |
| Score detail panel                                                |        |
| +-------------------------------+  +---------------------------+  |        |
| | Trend strength                |  | Reversal strength         |  |        |
| |   [SVG gauge: 72]             |  |   [SVG gauge: 34]         |  |        |
| |   Cross-sectional: Top 15%    |  |   Cross-sectional: Top 78%|  |        |
| |   2-year history: Top 22%     |  |   2-year history: Top 65% |  |        |
| |   3-year history: Top 18%     |  |   3-year history: Top 58% |  |        |
| |   --- 9 sub-items ---         |  |   --- 7 sub-items ---     |  |        |
| |   Momentum 10d:    78         |  |   RSI oversold:     12    |  |        |
| |   Momentum 20d:    71         |  |   RSI reversal:     45    |  |        |
| |   MACD hist:       65         |  |   KDJ oversold:     28    |  |        |
| |   MACD slope:      58         |  |   Bollinger Z (inv): 45   |  |        |
| |   SMA gold cross:  81         |  |   Mean reversion:   38    |  |        |
| |   EMA gold cross:  76         |  |   MA50 deviation:   42    |  |        |
| |   MA50 slope:      70         |  |   Negative mom 5d:  55    |  |        |
| |   MA50 deviation:  68         |  |                           |  |        |
| |   Bollinger pos:   62         |  |                           |  |        |
| +-------------------------------+  +---------------------------+  |        |
+------------------------------------------------------------------+        |
| Backtest panel (collapsed by default)                             |        |
+------------------------------------------------------------------+--------+
```

### 7.2 Dark-Theme Palette (TradingView premium style)

```css
:root {
    /* Background layers */
    --bg-primary: #131722;         /* Main background */
    --bg-secondary: #1e222d;       /* Card / panel background */
    --bg-tertiary: #2a2e39;        /* Input / hover background */
    --bg-elevated: #363a45;        /* Popover background */

    /* Text layers */
    --text-primary: #d1d4dc;       /* Primary text */
    --text-secondary: #787b86;     /* Secondary / label text */
    --text-muted: #4c525e;         /* Disabled / placeholder text */

    /* Accent colors */
    --accent-green: #26a69a;       /* Bullish / positive / golden cross */
    --accent-red: #ef5350;         /* Bearish / negative / death cross */
    --accent-blue: #2962ff;        /* Highlight / link / selection */
    --accent-yellow: #f7c948;      /* Warning / anomaly marker */
    --accent-purple: #ab47bc;      /* Special marker */

    /* Borders */
    --border-primary: #363a45;     /* Primary border */
    --border-subtle: #2a2e39;      /* Subtle separator */

    /* Chart-specific colors */
    --chart-candle-up: #26a69a;    /* Up candle */
    --chart-candle-down: #ef5350;  /* Down candle */
    --chart-volume: #5d6673;       /* Normal volume bar */
    --chart-volume-spike: #f7c948; /* Anomaly volume bar */
    --chart-ma-fast: #2196f3;      /* Fast MA */
    --chart-ma-slow: #ff9800;      /* Slow MA */
    --chart-bb-fill: rgba(33,150,243,0.05); /* Bollinger fill */
}
```

### 7.3 Interaction Design

- **Token selector:** searchable dropdown supporting fuzzy search by symbol and name. Selecting one updates all charts and scores in sync. Shows current price and 24h change.
- **Parameter tuning:** each indicator panel has number inputs at its top right. After modification, debounce for 300ms, then request fresh data from the backend and refresh the chart in real time. Next to the parameters is a "Reset" button to restore defaults.
- **Refresh button:** calls `POST /api/refresh`; the button turns into a spinner animation, polling `/api/status` until completion. Other interactions remain available during the refresh.
- **Chart timeline synchronization (must be implemented, not deferrable):** all charts share their time range. When the user zooms / drags the main K-line chart, all indicator charts below sync to match. Implementation: the main K-line chart is the master, listens to `subscribeVisibleTimeRangeChange`, and unidirectionally broadcasts to all slave sub-charts (calling `timeScale().setVisibleRange()`). A global `isSyncing` lock prevents event loops.
- **Ranking sidebar:** a 250px-wide collapsible panel on the right. Displays the Top 20 tokens, switchable between trend and reversal rankings. Clicking a token name switches the main view directly. Each token shows its score and a small trend sparkline.
- **Expand / collapse:** the 6 additional indicator families are collapsed by default; clicking "Show more indicators" expands them with a smooth animation.
- **Mobile adaptation:** under `@media (max-width: 768px)`, all panels become single-column and the sidebar becomes a drawer that can be pulled up from the bottom.

---

## 8. API Endpoint Design

| Endpoint | Method | Description | Response shape |
|----------|--------|-------------|----------------|
| `/api/tokens` | GET | List of all tracked tokens | `[{id, symbol, name, price, mcap, rank, has_binance}]` |
| `/api/token/{coin_id}` | GET | Token details + latest values of all indicators + scores | `{info, indicators, scores}` |
| `/api/ohlc/{coin_id}` | GET | K-line OHLC time series | `[{time, open, high, low, close, volume}]` |
| `/api/indicators/{coin_id}/{family}` | GET | Chart time series for a family. Supports overrides like `?fast=5&slow=20` | `{params, current, chart_data}` |
| `/api/indicators/{coin_id}` | GET | Current-value summary for all families | `{family_name: {indicator: value}}` |
| `/api/scores/{coin_id}` | GET | Trend + reversal scores + three percentiles | `{trend, reversal, percentiles}` |
| `/api/rankings` | GET | Market-wide ranking. `?sort_by=trend|reversal&limit=20` | `[{id, symbol, score, percentile}]` |
| `/api/backtest/{coin_id}` | GET | Golden-cross backtest. `?fast=5&slow=20&start=2023-01-01` | `{stats, equity_curve}` |
| `/api/refresh` | POST | Trigger a manual data refresh | `{status: "started"}` |
| `/api/status` | GET | System status | `{last_update, token_count, status, errors}` |
| `/api/data-check` | GET | Data-consistency validation results | `{alignment, missing, anomalies}` |

---

## 9. Implementation Steps

### Phase 1: Data-Layer Foundations

| Step | Task | Key files | Acceptance criteria |
|------|------|-----------|---------------------|
| 1.1 | Create project skeleton + `config.py` (all constants) | `config.py` | All parameter constants editable from a single file |
| 1.2 | Implement `exclusion.py` (token exclusion) | `exclusion.py` | Output is identical to notebook cell 2 |
| 1.3 | Implement `exchange_client.py` (CCXT multi-exchange OHLCV) | `exchange_client.py` | Binance→OKX→Bybit→Gate.io waterfall fallback; BTC/ETH/PI all fetchable |
| 1.4 | Implement `coingecko_client.py` (token list + market cap + fallback) | `coingecko_client.py` | Top 200 list + close-only data for the few fallback tokens |
| 1.5 | Implement `symbol_mapping.py` (ID ↔ multi-exchange symbol mapping) | `symbol_mapping.py` | CCXT auto-detection + manual augmentation, OHLC coverage > 97% |
| 1.6 | Implement `local_store.py` (CSV read/write, atomic writes) | `local_store.py` | Full writes; incremental append (atomic rename); integrity checks |
| 1.7 | Implement `fetcher.py` (data-fetching orchestrator) | `fetcher.py` | Full fetch of 200 tokens (including 3y history) + incremental 1-day update + resume-on-failure |
| 1.8 | Implement `data_validator.py` (consistency validation) | `data_validator.py` | Date-alignment detection, missing-day detection, price-anomaly detection, cross-source comparison |
| 1.9 | End-to-end data-layer test | Test scripts | BTC/ETH prices fully match the exchange's official site; PI is fetched from OKX |

### Phase 2: Indicator Engine

| Step | Task | Key files | Acceptance criteria |
|------|------|-----------|---------------------|
| 2.1 | Implement the `base.py` abstract base class | `base.py` | Defines the `compute()` and `compute_chart_series()` interfaces |
| 2.2 | Implement the SMA cross family | `ma_cross_sma.py` | Golden / death-cross events match TradingView |
| 2.3 | Implement the EMA cross family | `ma_cross_ema.py` | Same as above |
| 2.4 | Implement the MACD family | `macd.py` | MACD values within 0.1% of TradingView |
| 2.5 | Implement the RSI family | `rsi.py` | RSI values within 1 of TradingView (note Wilder smoothing) |
| 2.6 | Implement the RSI mean-reversion family | `rsi_mr.py` | Oversold-distance signal is correct |
| 2.7 | Implement the KDJ family (new) | `kdj.py` | KDJ values match Tongdaxin / TradingView |
| 2.8 | Implement the Bollinger Bands family | `bollinger.py` | %B and Z-score correct |
| 2.9 | Implement the volume-anomaly family | `volume_spike.py` | 3x-anomaly detection matches manual reconciliation |
| 2.10 | Implement the momentum family | `momentum.py` | Return computation is correct |
| 2.11 | Implement the mean-reversion (skip) family | `mean_reversion.py` | Z-score matches notebook output |
| 2.12 | Implement the Z-Score vs MA50 family | `zscore_ma.py` | MA50 deviation matches manual computation |
| 2.13 | Implement the price-appreciation family | `price_appreciation.py` | Joint volume-price-event detection is correct |
| 2.14 | Implement `registry.py` | `registry.py` | All 12 families registered and lookup-by-name works |

### Phase 3: Scoring + Ranking + Backtest + API

| Step | Task | Key files |
|------|------|-----------|
| 3.1 | Implement `trend_score.py` (trend score, 9 signals) | `trend_score.py` |
| 3.2 | Implement `reversal_score.py` (reversal score, 7 signals) | `reversal_score.py` |
| 3.3 | Implement `ranking.py` (cross-sectional + 2y/3y time-series percentiles + `scores_history.csv` persistence) | `ranking.py` |
| 3.4 | Implement `golden_cross.py` (golden-cross backtest) | `golden_cross.py` |
| 3.5 | Implement all API routes | `routes_*.py` |
| 3.6 | Implement `main.py` (FastAPI + APScheduler at UTC+8 08:30) | `main.py` |

### Phase 4: Frontend

| Step | Task |
|------|------|
| 4.1 | HTML skeleton + dark-theme CSS (TradingView premium style) |
| 4.2 | Token selector (searchable dropdown + price / change display) |
| 4.3 | Main K-line candle chart (Binance OHLC + Lightweight Charts) |
| 4.4 | 6 core indicator chart panels (with parameter tuning) |
| 4.5 | 6 additional indicator chart panels (collapsed by default) |
| 4.6 | Score dashboard (SVG gauge + three percentiles + sub-item breakdown) |
| 4.7 | Ranking sidebar (Top 20 + sparkline + switch main view) |
| 4.8 | Backtest panel (collapsible + equity-curve chart) |
| 4.9 | Mobile adaptation (media queries + single-column layout) |

### Phase 5: Deployment and Testing

| Step | Task |
|------|------|
| 5.1 | `requirements.txt` + `run.sh` + `.env` |
| 5.2 | macOS launchd autostart configuration |
| 5.3 | Full verification process (see Chapter 11) |

---

## 10. Deployment Plan

### 10.1 Dependencies

```
fastapi>=0.115
uvicorn[standard]>=0.30
pandas>=2.2
numpy>=1.26
scipy>=1.12
requests>=2.31
ccxt>=4.0                   # unified multi-exchange API access (Binance/OKX/Bybit/Gate.io)
apscheduler>=3.10
python-dotenv>=1.0
```

### 10.2 Environment Variables (`.env` file)

```
COINGECKO_API_KEY=Your Pro API Key
UPDATE_HOUR=8
UPDATE_MINUTE=30
UPDATE_TIMEZONE=Asia/Shanghai
DATA_DIR=./local_data
BACKUP_KEEP=3
```

### 10.3 Launch

```bash
cd crypto-tech-dashboard
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m backend.main   # or: uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

### 10.4 macOS Autostart

Configured via a `launchd` plist placed at `~/Library/LaunchAgents/com.iosg.crypto-dashboard.plist`.

---

## 11. Detailed Validation Plan

### 11.1 Data-Source Reliability Validation

| Check | Method | Expected result | Frequency |
|-------|--------|-----------------|-----------|
| **Multi-exchange connectivity** | Call CCXT's `load_markets()` against Binance / OKX / Bybit / Gate.io respectively | At least 3 of 4 exchanges available | Before each update |
| **Binance rate-limit detection** | Monitor CCXT's `rateLimit` mechanism; ensure no 429 errors | A single update of 200 tokens runs without rate-limit errors | During each update |
| **OKX / Bybit / Gate.io rate-limits** | Same as above; CCXT handles each exchange's rate-limit automatically | Fallback-token fetches run without errors | During each update |
| **CoinGecko API availability** | Call `/api/v3/ping` and verify a normal response | HTTP 200 | Before each update |
| **CoinGecko rate-limit** | Pro plan = 500 req/min | A single update is ~10 requests (token list + ~5 fallback tokens) | During each update |
| **API key validity** | At first start-up, test CoinGecko's auth endpoint | Returns non-401 / non-403 | At start-up |
| **Trading-pair existence** | Refresh each exchange's available pairs via CCXT's `load_markets()` and compare against the mapping table | Delisted pairs automatically degrade to the next exchange | Once a week |
| **CCXT version compatibility** | Check whether the CCXT version supports the latest APIs of all 4 exchanges | `pip show ccxt` version >= 4.0 | Once a month |

### 11.2 Data Date-Alignment Validation

| Check | Method | Treatment |
|-------|--------|-----------|
| **Binance date standard** | Take BTC's latest 3 days of klines; verify `openTime` is the millisecond timestamp of UTC 00:00:00 | If not UTC 00:00, record the offset |
| **CoinGecko date offset** | Take BTC's last 30 days of CoinGecko close prices; cross-check against Binance Close | Compute the best offset (0 days or ±1 day); log to `data_integrity_log.json` |
| **Automatic date-offset correction** | If CoinGecko needs a 1-day shift, automatically shift when reading market-cap data | Hard-code a configurable parameter `CG_DATE_OFFSET` |
| **Weekend / holiday handling** | Binance trades 24×7, no closure. Same for CoinGecko. But check whether any token has missing data on certain days | Forward-fill the missing day with the previous day |

### 11.3 Cross-Source Close-Price Consistency Validation

| Check | Method | Tolerance |
|-------|--------|-----------|
| **Exchange Close vs CoinGecko Close** | For 10 mainstream tokens (BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, DOT, LINK), compare exchange OHLCV Close against CoinGecko close over the last 30 days | < 0.5% normal; > 1% triggers an alert |
| **Cross-exchange consistency** | For the same token (e.g. ETH), fetch the last 30 days of Close from Binance and OKX respectively | < 0.1% (both exchange-sourced, should match closely) |
| **Time-zone alignment confirmation** | Verify that every exchange slices daily candles at UTC 00:00 | CCXT handles this uniformly, but spot-check is required |
| **Cross-source impact on indicator computation** | Compute BTC's RSI(14) using Binance and CoinGecko close prices respectively; compare | RSI difference < 1 |

### 11.4 Volume Data Validation

| Check | Method | Expected |
|-------|--------|----------|
| **Non-zero exchange volume** | Check whether any token has volume=0 days in the last 30 days | Mainstream tokens should not have zero volume |
| **Cross-exchange volume comparison** | For BTC, fetch Binance and OKX volume respectively; verify they are of the same magnitude | Volumes on the same pair across different exchanges may differ, but daily-trend direction should match |
| **VolumeSpike sanity** | Compute BTC's `vol_spike_3x` events over the last 1 year; manually verify they correspond to known events (e.g. ETF-approval days) | Anomaly days should coincide with known market events |
| **CoinGecko-fallback token volume** | Fallback tokens use CoinGecko aggregated volume; annotate the differing data source | The frontend labels it "aggregated volume"; the volume signals still participate normally in scoring |

### 11.5 Local File-Cache Validation

| Check | Method | Expected |
|-------|--------|----------|
| **CSV file integrity** | At start-up, for each CSV check: row count > 0, no duplicate dates, monotonically increasing dates, no NaNs in key columns | All pass |
| **Incremental-update correctness** | After an incremental update, check that the last-row date = yesterday (UTC) and equals the API value | Fully consistent |
| **File lock / concurrency safety** | During an update, simultaneously read the CSV (simulated API request) to ensure no half-written state is read | The in-memory DataFrame serves requests; CSV is not read directly |
| **Backup integrity** | After a full backfill, verify that the backup directory exists and has the same number of files as the original | Matches |
| **Disk space** | Check the total size of the `local_data/` directory | < 50MB |
| **Corruption recovery** | Manually delete one CSV; after restart, that token's data should be automatically re-fetched | Missing data is detected automatically and re-fetched |

### 11.6 Indicator-Computation Correctness Validation

| Check | Method | Tolerance |
|-------|--------|-----------|
| **RSI(14) vs TradingView** | Take BTC's latest RSI; compare manually against TradingView | < 1 (because Wilder smoothing's initial-value handling may differ slightly) |
| **MACD(12,26,9) comparison** | Take BTC's latest MACD histogram; compare against TradingView | < 0.1% (on the normalized value) |
| **BB(20,2) comparison** | Take BTC's latest BB upper/lower/middle bands; compare against TradingView | < 0.01% |
| **KDJ(9,3,3) comparison** | Take BTC's latest K/D/J values; compare against Tongdaxin or TradingView | < 2 (KDJ initial-value differences can be larger) |
| **Golden / death-cross events** | In BTC's last 1 year of data, find all SMA(5,20) golden-cross events; manually verify each on TradingView | All event dates match exactly |
| **Comparison against notebook output** | Run `compute_features()` from the last cell of `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` on BTC; compare with the Dashboard's results indicator by indicator | < 1e-6 (floating-point precision) |

### 11.7 Score and Ranking Validation

| Check | Method | Expected |
|-------|--------|----------|
| **Trend-score sanity** | Find recent strong performers (e.g. Top 5 gainers); verify their trend score should be 80+ | Trend score > 80 |
| **Reversal-score sanity** | Find recent heavy losers; verify their reversal score should be relatively high | Reversal score > 70 |
| **Cross-sectional ranking consistency** | The trend-rank percentile of all 200 tokens should be uniformly distributed over 0–100 | Approximately uniform distribution |
| **Time-series ranking** | Take BTC's current trend score; manually compute its percentile within the last 2 years | Matches the API value |
| **Edge cases** | A newly listed token (< 2 years of history) should have its 2-year / 3-year ranks marked "insufficient data" | Correctly annotated |

### 11.8 Frontend-Interaction Validation

| Check | Method |
|-------|--------|
| **Token switching** | Switch from BTC to ETH; all 12 charts + scores + ranking should update |
| **Parameter changes** | Change MACD from (12,26,9) to (5,10,4); the chart should refresh within 1 second |
| **Chart timeline sync** | Zoom the main K-line chart to the last 30 days; all sub-charts sync |
| **Ranking sidebar** | Click SOL in the sidebar; the main view should switch to SOL |
| **Manual refresh** | Click refresh; the button shows a spinner; once complete the data updates automatically |
| **First-start experience** | On first start, an "Initializing data…" progress indicator is displayed; afterwards it renders normally |
| **Mobile** | Chrome DevTools simulating iPhone 12; verify single-column layout and basic usability |

### 11.9 Auto-Update Validation

| Check | Method |
|-------|--------|
| **Scheduled trigger** | Change the time to 1 minute in the future; verify APScheduler triggers on time |
| **Incremental-update correctness** | After an update, check that the last-row date of the CSV is correct and matches the API value |
| **Frontend availability during update** | While the background update is running, access the frontend; confirm it returns old data rather than errors |
| **Data switchover after update** | After the update completes, the frontend shows data for the new date |
| **Multi-day consecutive updates** | Simulate updates for 3 consecutive days (manual trigger × 3); confirm data accumulates correctly |
| **Abnormal recovery** | During an update, simulate a network outage (disconnect WiFi); after restart, verify it recovers normally |

### 11.10 Edge-Case and Error-Handling Validation

| Check | Treatment |
|-------|-----------|
| **Tokens unavailable on any exchange** | Waterfall fallback Binance → OKX → Bybit → Gate.io → CoinGecko (~5 tokens); KDJ shows N/A for fallback tokens |
| **New token entering Top 200** | Automatically create CSV file and full-fetch historical data |
| **Token leaving Top 200** | Keep the data but mark inactive; stop updating |
| **Token renamed / changes symbol** | Identified via the (immutable) CoinGecko ID; symbol changes do not affect us |
| **Exchange pair delisted** | When CCXT returns empty data, automatically degrade to the next exchange (waterfall fallback) |
| **Flash crash / abnormal price** | Detect intraday amplitude > 50%; mark but do not delete |
| **API rate-limit error (429)** | Exponential backoff retry, up to 3 attempts at 2s/4s/8s |
| **API timeout** | 10-second timeout, 2 retries |
| **Disk full** | At startup, check that free space > 100MB; otherwise alert |
| **Unexpected process exit** | launchd's `KeepAlive` automatically restarts; at startup, state is recovered from local files |
