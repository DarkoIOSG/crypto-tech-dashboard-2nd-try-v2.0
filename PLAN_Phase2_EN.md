# Phase 2 Plan — Technical Indicator Dashboard (Phase 2 Plan)

> Translated from `二期Plan-技术指标Dashboard.md`. This is the Phase-2 implementation plan (11 user-requested improvements + 4 role-based audits).

> **Status**: Finalized (pending ExitPlanMode approval)
> **Written on**: 2026-05-14
> **Current Git HEAD**: `814b530` (R7-8 fix retry path for failed_ids)
> **Once implementation begins this file will be re-saved as**: `crypto-tech-dashboard-2nd-try/二期Plan-技术指标Dashboard.md`
> **Total items**: 11 improvement items + 3 R6/R7 carryover bugs = 14 atomic units of work
> **Estimated cycle**: 4 weeks × 4 phases (an independent audit runs at the end of each phase)

---

# Part 0 — Context (Why we are doing Phase 2)

Phase 1 (R1–R7) ran 7 iteration rounds and landed the core requirements of `PLAN_技术指标Dashboard.md` §1–§11 down at the code level: 12 indicator families + 9+7 scoring signals + 2y/3y time-series percentiles + data layer + APScheduler scheduling + 21 light-palette CSS variables + mobile layout + UX polish. The Quant + System Engineer R7 verdict was `SHIP`; the Artist + Aesthetician R7 verdict was `NEEDS-POLISH (49/65)`.

The system is shippable, but the user has raised **11 improvement directions + 4 role perspectives**:

1. **The scoring system is not "user-friendly" enough** (items 1, 2, 9) — the dual Trend / Reversal numbers confuse users; no integrated judgement is provided.
2. **Insufficient data breadth** (items 7, 11) — only crypto Top-200 is covered, with no US stocks; OHLCV only goes back to 2023-05-15, but it must reach 2020-01-01.
3. **Data localisation + reliability** (item 10) — `main.py` has a portability bug; incremental writes and corruption recovery are needed.
4. **Missing market-fundamentals information** (item 5) — there is no market-cap ranking, liquidity, or 30-day average volume.
5. **Visual immersion** (items 3, 4, 8) — no light mode, residual Chinese, tooltips not rich enough.
6. **Indicator-reliability transparency** (item 6) — users do not know whether a given indicator made or lost money historically.

Phase 2 is organised around these requirements, **executed verbatim from the user's wording**.

---

# Part 1 — Original 11 User Requirements (verbatim)

> Below are **verbatim quotations** of the user from the Phase-2 prompt. My interpretation and proposal are in Part 4 — the original text is locked in here as the single source of truth.

### User verbatim, item 1 — Optimise the Score display

> *The current Momentum Score and Reversal Score are quite confusing to users.*
> *(a) Clarify the specific meaning and strengths of these two scores.*
> *(b) Add a comparison dimension that shows the token's current ranking inside the Top 200.*
> *(c) Add explanations of the calculation logic in the charts.*

### User verbatim, item 2 — Build a composite scoring system

> *Because we currently have two indicators, Momentum and Reversal, users find it hard to arrive at a composite judgement.*
> *(a) From the perspective of a professional quant researcher and financial analyst, design a composite scoring scheme.*
> *(b) Consider introducing something like Transformer or related algorithms, scoring against "tradable behaviour".*
> *(c) The score should be optimised from the trend in momentum and reversal changes.*

### User verbatim, item 3 — Add a light mode

> *Add a mode-switch icon (e.g. sun / moon) in the top-right of the system, supporting toggling from dark mode to a white (light) page.*

### User verbatim, item 4 — Full English version

> *The system still contains some Chinese content. Convert all Chinese content (including indicator names, common variable names, etc.) to English — make sure no Chinese characters remain.*

### User verbatim, item 5 — Add token market-cap and liquidity data

> *Add a panel in the system for inspecting the token's real-time quote:*
> *(a) Market-cap rank and the absolute market cap (Market Cap).*
> *(b) Liquidity data.*
> *(c) 30-day average volume.*

### User verbatim, item 6 — Indicator robustness analysis

> *From an analyst's perspective, analyse how the current indicators have performed on historical data.*
> *(a) Backtest the key buy / sell points (e.g. golden-cross / death-cross strategies).*
> *(b) Evaluate whether trading exactly per the indicator would have been profitable or loss-making historically, thereby judging its reliability.*

### User verbatim, item 7 — Add US stocks

> *The system currently only supports two stocks; we now need to expand the number, especially HK and US stocks. Please research relevant information on these stocks via Yahoo Finance.*
>
> *Stock data was obtained from Yahoo Finance, providing coverage for 40 publicly traded cryptocurrency-related companies:*
>
> `['ANY', 'APLD', 'ARBK', 'BIGG', 'BITF', 'BKKT', 'BLSH', 'BTBT', 'BTCS', 'BTDR', 'BTGO', 'BTM', 'CAN', 'CIFR', 'CLSK', 'COIN', 'CORZ', 'CRCL', 'DEFT', 'DMGGF', 'EBON', 'ETOR', 'EXOD', 'FIGR', 'FLD', 'GEMI', 'GLXY', 'GREE', 'HIVE', 'HOOD', 'HUT', 'IREN', 'MARA', 'MOGO', 'MSTR', 'NPPTF', 'RIOT', 'SMLR', 'VOYG', 'WULF']`

**Constraints after clarification** (Q5 + Q9): HK stocks deferred; only the 40 US stocks; default landing token = `CRCL`.

### User verbatim, item 8 — PowerTile / Hover state enrichment

> *I have noticed some PowerTiles (or Hover states) that show a question mark on mouse-over, proving the detailed information has not been filled in. Please optimise and complete this area.*

### User verbatim, item 9 — Overall Score composite panel

> *Regarding the composite assessment system I mentioned earlier — the resulting Overall Score should be placed at the very top, similar to the Momentum and Reversal indicators. It should be a composite-panel type.*

### User verbatim, item 10 — Local data persistence

> *The vast majority of the data should be stored in local folders. Take HK/US stocks as an example: if recent data has already been fetched, first back up the data locally, then update the database with incremental writes rather than re-reading everything every time. Otherwise, once the database is corrupted, robustness will be very poor.*

### User verbatim, item 11 — Crypto history extension

> *Regarding cryptocurrency (e.g. Bitcoin) data: currently only data from 2024 onward (the original mis-stated 2025) is shown — that does not meet my requirement.*
> *1. Goal: the data must go back to 2020-01-01.*
> *2. Logic:*
>    *(a) For tokens launched after 2020, fetch from the listing day onward.*
>    *(b) For stocks or tokens that existed before 2020, we must reach 2020-01-01.*
> *3. Storage: check all data sources; make sure data lives under the current folder. I want a "green" / portable folder that can be copied to another machine and run directly.*
>
> *Please think, as an architect, about how to extend the date range and improve system reliability. The default chart can still show only the last year of candles.*
>
> **Revision (2026-05-15, direct user instruction)**: cancel the "default 1 year" constraint. The default viewport directly displays **all history** (2020-01-01 → today for old coins; listing-day → today for new coins). `fitContent()` expands everything; the user can zoom / pan to a sub-range themselves.

### The 4-tier data-fetching logic proposed by the user (hard constraint given in the Q10 answer)

> *For data acquisition please follow this logic:*
> *1. First, fetch via CCXT as exhaustively as possible — obtain all the OHLC data we can get.*
> *2. If we cannot get it that way, check whether there is on-chain OHLC data available.*
> *3. If on-chain is not available either, then try scraping (web-scrape) the data.*
> *4. If still unavailable, fall back to the first approach we discussed and back-fill the previous data.*
>
> *Also, you need to annotate this: clearly mark from which time onward the data is correct — this must be made explicit.*

**After clarification** (Q13): Tier 2 (on-chain) and Tier 3 (scraping) are skipped; only Tier 1 (CCXT exhaustive) + Tier 4 (CG close-only) are kept. **However, per-token data-quality boundary metadata must be preserved and exposed in the UI** (Q14 decision).

---

# Part 2 — 16 Clarification Q&A (verbatim)

> This section records the user's reply to each question **verbatim** as the basis for decisions.

### Q1 — Composite-score tier

**Question**: Tier A hand-weighted / Tier B Ridge regression / Tier C ML / A now & B next sprint — which one?
**User answer**: *"Do both A and B, because I'm not sure B can do well in one shot."*
**Decision**: Tier A lands in Phase 2B, Tier B lands in Phase 2D, sharing the same API fields; the front-end switches between them via a Toggle.

### Q2 — Tooltip style

**Question**: Native `title` / native + local popover / fully custom popover — which?
**User answer**: *"Native + local popover (the recommended compromise)."*
**Decision**: The 12 panel headers + 7 param labels use native `title`; the 16 Score-Breakdown component rows + the Overall card use an 80-line lightweight popover (200 ms hover delay, doesn't dismiss while hovering inside, optional "Methodology →" link).

### Q3 — Light-palette character

**Question**: Two-layer off-white / pure white / warm grey — which?
**User answer**: *"Follow the TradingView white style — the colour combinations should feel very premium."*
**Decision**: Two-layer off-white: canvas `#F0F3FA` (pale blue-grey) + card `#FFFFFF` (pure white). Accent colours are darkened to meet WCAG AA: `--accent-green` from `#26a69a` to `#089981`; `--accent-yellow` from `#f7c948` to `#B8860B` (the original values are unreadable on white).

### Q4 — Overall-card layout

**Question**: Strategy A full-width hero + two columns below / Strategy B three equal columns / Strategy C vertical three-stage — which?
**User answer**: *"Strategy A: full-width hero on top + two columns below (recommended)."*
**Decision**: Full-width hero card on top; below, keep the existing two-column Trend + Reversal grid. The Overall gauge is 240 px (~40% larger than the 170 px below); the big number is 56 px (vs 38 px below); a 2 px `--accent-blue` accent border on the left; the title adds a 9 px uppercase `COMPOSITE` micro-badge.

### Q5 — Include HK stocks in Phase 2?

**Question**: 5-ticker narrow / 12-ticker medium / custom?
**User answer**: *"I already sent you the US-stock list (40 tickers). Default = CRCL, right?"*
**Decision**: HK stocks **deferred to Phase 3**. Phase 2 has only the 40 US stocks. Default landing token = CRCL.

### Q6 — Mixed crypto+stock ranking, or split?

**Question**: Fully split / mixed / split but keep an "All" tab?
**User answer**: *"Fully split (recommended)."*
**Decision**: Crypto 200 and stocks 40 each have an independent cross-section ranking. The sidebar has two tabs: `[Crypto (200)]` `[US Stocks (40)]`. Tab state is saved to the URL hash.

### Q7 — Overall card breakdown content

**Question**: 6 sleeves / Top-6 contributors / both?
**User answer**: *"6 sleeves (A, recommended, abstract)."*
**Decision**: Below the Overall card, show 6 sleeves plus each one's weighted contribution: Trend / Reversal / Signal Breadth / Risk / Trend TS 2y / Reversal TS 2y.

### Q8 — Implementation order of the 11 items

**Question**: Architecture-first / user-value-first / three tracks in parallel?
**User answer**: *"Architecture-first (Plan B, recommended)."*
**Decision**: Phase 2A (10/11/5/7) → Phase 2B (2A/6/1) → Phase 2C (9/3/4/8 + R6/R7 carryover) → Phase 2D (2B + final acceptance).

### Q9 — Final HK decision

**User answer**: *"Just the 40 I gave you — I may have mis-spoken; no HK stocks."*
**Decision**: Consistent with Q5. HK is skipped entirely in Phase 2.

### Q10 — Pre-2023 crypto data

**Question**: Close-only fallback / strict purism / Top-50 backfill only?
**User answer**: *"First, fetch exhaustively via ccxt, following the first approach you preferred, dealing with multiple exchanges. You can accept close-only, but for any particular token you must state from when (the data is valid)."* + the 4-tier data-fetching logic.
**Decision**: Tier 1 CCXT exhaustive + Tier 4 CG close-only. Write `data_coverage.json` metadata per token; the UI exposes a "Data Coverage" collapsible in the scoring area.

### Q11 — Scope of English-isation

**Question**: User-visible only / + backend comments+log / + docs?
**User answer**: *"Include backend code comments + log."*
**Decision**: Chinese in any `.py`, `.js`, `.html`, `.css` file is translated to English. Docs (README / PLAN / hand-off guide) stay in Chinese. Commit history is not rewritten either.

### Q12 — Acceptance approach

**Question**: One round per module / one round at the end / smoke test only?
**User answer**: *"Run a round of acceptance after each large module is done (recommended)."*
**Decision**: 4 audit rounds (R8-α data architect + system engineer; R8-β quant + designer; R8-γ artist + analyst; R8-δ quant final).

### Q13 — Tier 2/3 sources

**Question**: Only Tier 1+4 / TheGraph / CMC / all?
**User answer**: *"Only Tier 1 (CCXT) + Tier 4 (CG close-only); skip on-chain and scraping."*
**Decision**: Phase-2 data sources use Tier 1 + Tier 4 only. CCXT is, however, expanded to 8 exchanges (Binance / OKX / Bybit / Gate.io + Coinbase / Kraken / KuCoin / Bitstamp) to realise "exhaustive".

### Q14 — Data-quality boundary UI

**Question**: Collapsible in the scoring area / dashed candles / both / API only?
**User answer**: *"An extra 'Data Coverage' small collapsible in the scoring area (recommended)."*
**Decision**: Below the token-meta in the scoring area, add a line "Data Coverage: Exchange OHLC from 2023-05-15 · Close-only history back to 2020-01-01 · KDJ/Volume valid from 2023-05-15"; clicking expands to display the tier-distribution table.

### Q15 — R6/R7 carryover bugs

**Question**: Fix all / only mobile drawer / skip all?
**User answer**: *"Fix all of them (recommended)."*
**Decision**: R6-7 mobile drawer + R7-3 gauge 0/100 label clipping + R7-4 indicator-panel right price-axis chip overlap are all fixed in Phase 2C.

### Q16 — Timing of Tier B

**Question**: Phase 2D / Phase 3 / never?
**User answer**: *"Land it together in Phase 2D (consistent with Plan agent A's recommendation)."*
**Decision**: Consistent with Q1.

---

# Part 3 — Deep Analysis from Three Role Perspectives (user-required, item 4)

## 3.1 Financial-analyst + quant-researcher view

### Issues with the current scoring system (user verbatim items 1 + 2)

The Trend score is a cross-sectional percentile-weighted mix of 9 signals; the Reversal score is the same for 7 signals. Both output 0–100; faced with two such numbers, users do not know what to do:
- BTC currently has Trend = 41.2, Reversal = 55.0. **Is this good or bad?** The user cannot tell.
- There is no explicit "rank N in 200 tokens".
- There is no formula explanation: the user does not know that Trend is a mix of SMA/EMA/MACD/momentum, and Reversal is a mix of RSI/KDJ/Bollinger/mean-reversion.

### Quant proposal: Tier A — hand-weighted

**Formula (finance-theory prior weights, Liu/Tsyvinski 2021 + Russell/Engle 2010)**:

```
Overall = 0.40 · Trend (CS percentile)
        + 0.25 · Reversal (CS percentile)
        + 0.15 · Breadth (% of 9 trend signals > 0, CS percentile)
        + 0.10 · Risk (1 / vol_20d, CS percentile, low-vol = high score)
        + 0.10 · TS_Trend_2y · 0.5
        + 0.10 · TS_Reversal_2y · 0.5
```

**Justification of the weights**:
- Trend = 0.40: in crypto, momentum is the most robust factor (Liu/Tsyvinski 2021, "Risks and Returns of Cryptocurrency").
- Reversal = 0.25: real but noisy — in crypto, the probability that a token keeps falling after a 25% bounce is not low.
- Breadth = 0.15: consistency across multiple signals (Russell/Engle co-movement discount).
- Risk = 0.10: penalises high-volatility moonshots (vol-adjusted return = Sharpe-like).
- TS history = 0.10: captures "rare strength outliers"; in the long run a token that has been at the BTC 2y high for a long time is more reliable than one that has just spiked.

**Walk-forward validation (accept gate)**:

```
For each historical date in scores_history.csv:
  - Compute Tier A composite
  - Compute forward 5d / 10d / 20d return per token
  - Spearman rank correlation per horizon

Accept if: ρ(Overall, forward_5d_return) ≥ ρ((Trend+Reversal)/2, forward_5d_return) + 0.05
```

### Quant proposal: Tier B — Ridge empirical weights

**Goal**: use real historical data to drive the weights, answering "why should Trend be 40% rather than 50%".

**Implementation**:
- Pooled panel Ridge with date-fixed effects.
- 24-month train / 1-month test / monthly rolling.
- All 16 atomic-signal CS percentiles + the 4 sleeves go into the feature set.
- Target: per-token per-day forward 5-day log return.
- `sklearn.linear_model.RidgeCV(alphas=[0.1, 1, 10, 100])`.
- 12-fold stability: drop any feature whose coefficient sign flips.

**Acceptance criterion**: Tier B hold-out Spearman ρ ≥ Tier A baseline + 0.02. If it does not reach this, **the acceptance fails, Tier A stays as production**, and the front-end hides the Tier B Toggle.

### Quant proposal: indicator robustness backtest (item 6)

For each of the 9 indicator families design one canonical strategy, then run a universe-wide backtest:

| Strategy name | Entry | Exit |
|---|---|---|
| `rsi_oversold_30_50` | RSI < 30 | RSI > 50 |
| `macd_signal_cross` | MACD line crosses signal up | crosses down |
| `kdj_oversold_cross` | K crosses D up while both < 20 | K crosses D down while both > 80 |
| `bollinger_lower_band` | close touches the lower band (pctb<0) | close touches the middle band (pctb=0.5) |
| `sma_golden_cross` | SMA(5) > SMA(20) | SMA(5) < SMA(20) |
| `ema_golden_cross` | EMA(5) > EMA(20) | EMA(5) < EMA(20) |
| `momentum_breakout` | 20d return > 0 | 20d return ≤ 0 |
| `zscore_reversion` | z-score < -2 | z-score > 0 |
| `price_appreciation` | 20d return > 10% AND vol_z > 2 | 5d return < 0 |

Universe-wide aggregation per strategy:
- median Sharpe
- mean Sharpe
- pct positive Sharpe
- worst case (Sharpe, cg_id)
- best case (Sharpe, cg_id)

**Reliability-badge thresholds (calibrated for crypto, BTC buy-hold Sharpe ≈ 1.1)**:
- **Reliable**: median Sharpe ≥ 0.5 AND ≥ 60% positive AND worst ≥ -1.0.
- **Useable with caveats**: median Sharpe ∈ [0.2, 0.5) OR pct positive ∈ [50%, 60%).
- **Unreliable**: median Sharpe < 0.2 OR pct positive < 50%.

### Quant proposal: rank-in-universe display (item 1b)

`/api/scores/{id}` adds:
- `rank_in_universe_trend: int (1..N)`
- `rank_in_universe_reversal: int (1..N)`
- `rank_in_universe_overall: int (1..N)`
- `universe_size: int`

The UI shows next to each score-card title: `Rank 47 / 200`; hovering reveals "Top 23.5% in 200-token universe today".

### Quant proposal: calculation-logic explainer (item 1c)

New module `backend/scoring/explainers.py`:

```python
TREND_EXPLAINER = {
    "title": "Trend Score",
    "one_line": "Blended SMA / EMA / MACD / momentum signals, ranked cross-sectionally.",
    "formula_md": "Trend = equal-weighted mean of 9 signal percentiles, then rank-percentile across the 200-token universe.",
    "signal_table": [
        {"key": "mom_ret_10d", "label": "Momentum (10d)", "current": <value>, "weight": 1.0},
        {"key": "mom_ret_20d", "label": "Momentum (20d)", "current": <value>, "weight": 1.0},
        ...9 rows...
    ],
    "strengths": [
        "Captures persistent trends across multiple timeframes",
        "Robust against single-indicator failure",
        ...
    ],
    "weaknesses": [
        "Lags reversal points by ~5-10 days",
        "False signals in choppy markets",
        ...
    ],
    "interpretation": {
        "above_70": "Strong uptrend across most signals — momentum continuation likely.",
        "30_70": "Mixed signals — wait for confirmation.",
        "below_30": "Weak / downtrending — avoid long entries."
    }
}
```

New route `GET /api/scoring/explainer` returns the three explainers — Trend / Reversal / Overall. On the front end, clicking the `.info-mark` `?` opens a modal popover that displays the explainer + the current token's real-time `signal_table` values.

---

## 3.2 System-architect + data-scientist view

### Data-layer architecture (items 10 + 11)

**Current problems** (discovered by Plan agent B):
- `backend/main.py:57` hard-codes `LocalStore(Path(PROJECT_ROOT) / "local_data")`, **ignoring** the `DATA_DIR` variable in `.env`. This is the prerequisite bug for "green folder" (P0 portability).
- All 200 OHLCV CSVs have earliest date 2023-05-15 (Phase 1 `HISTORY_DAYS=1095`).
- `top200_current.csv` has only 5 columns — no market_cap_rank / total_volume / liquidity proxy.
- No yfinance integration; stocks are completely blank.
- No boot-time integrity check; corrupted CSVs are not detected.

**4-tier waterfall implementation** (after Q10 + Q13 decisions):

```
Tier 1: CCXT 8-exchange waterfall
  Binance → OKX → Bybit → Gate.io → Coinbase → Kraken → KuCoin → Bitstamp
  per-call pagination via since= cursor (cap 4000 days)
  maximises OHLC coverage

Tier 2: skip
Tier 3: skip

Tier 4: CoinGecko close-only fallback
  /coins/{id}/market_chart/range — single-shot full range
  fill O=H=L=Close, volume=0, source="coingecko"
  KDJ / Volume Spike automatic NaN-guard
```

**Per-token data-coverage metadata** (per user request item 11.3 + Q14):

New file `local_data/metadata/data_coverage.json`:

```json
{
  "bitcoin": {
    "earliest_date": "2017-01-01",
    "latest_date": "2026-05-13",
    "listing_date": "2009-01-09",
    "real_ohlc_from": "2017-08-15",
    "close_only_windows": [],
    "tier_breakdown": [
      {"from": "2017-08-15", "to": "2021-12-31", "tier": 1, "source": "binance", "rows": 1599},
      {"from": "2022-01-01", "to": "2023-05-14", "tier": 1, "source": "okx", "rows": 499},
      {"from": "2023-05-15", "to": "2026-05-13", "tier": 1, "source": "okx", "rows": 1095}
    ]
  },
  "spiko-amundi-overnight-swap-fund-eur": {
    "earliest_date": "2024-03-21",
    "latest_date": "2026-05-13",
    "listing_date": "2024-03-21",
    "real_ohlc_from": null,
    "close_only_windows": [["2024-03-21", "2026-05-13"]],
    "tier_breakdown": [
      {"from": "2024-03-21", "to": "2026-05-13", "tier": 4, "source": "coingecko", "rows": 783}
    ]
  }
}
```

New API: `GET /api/data-coverage/{cg_id}` returns coverage info for a single token.

### Stocks-integration architecture (item 7)

**Option 3 (lightest, recommended by Plan agent B + Q6 decision)**:

- `local_data/metadata/stocks_universe.csv`: 40 rows of US tickers + an `asset_class` field.
- `backend/data/yfinance_client.py`: mirror of the `coingecko_client` interface:
  ```python
  class YFinanceClient:
      def fetch_universe_metadata(tickers) -> pd.DataFrame
      def fetch_ohlcv(ticker, start, end) -> Optional[pd.DataFrame]
      def fetch_market_overview(ticker) -> dict
  ```
- Use `yf.Ticker(ticker).history(auto_adjust=True, actions=False)`; `auto_adjust=True` folds in splits + dividends.
- Rename columns `Open/High/Low/Close/Volume` → `open/high/low/close/volume`; timezone `America/New_York`.
- `source = "yfinance"`.
- Cross-asset-class ranking **fully separated** (Q6 decision): `cross_sectional_percentile` partitions by `asset_class`.
- `_validators.validate_cg_id` regex is extended to allow A–Z and `.` (still rejecting `..` and `/`).

**Stocks daily-refresh schedule**: 5 minutes after the crypto 08:30 Asia/Shanghai job (08:35) the stocks job kicks off. Yfinance skips weekends + US-stock holidays, but same-day data is only available ~3 hours after US-stock close (i.e. ~04:00 next day Asia/Shanghai), so the data pulled at 08:35 is the full T-1 data — this timing aligns nicely.

### "Green-folder" packaging architecture (item 10)

**Fix + enhancement**:
1. **Fix `backend/main.py:57`**: `LocalStore(DATA_DIR)` replaces the hard-coded version (`DATA_DIR` is already resolved as a relative/absolute path in `config.py:74-79`).
2. **New `backend/data/integrity.py`**: at boot, validate every OHLCV CSV (see Part 4 for details).
3. **New `backend/data/quarantine/`**: corrupted CSVs are auto-moved here, not deleted.
4. **New `Fetcher.repair_token(cg_id)`** + `POST /api/admin/repair/{id}` (only 127.0.0.1).
5. **New `scripts/pack_green_folder.sh`**:
   ```bash
   zip -r dashboard_green_$(date +%Y%m%d).zip . \
     -x "venv/*" "*/__pycache__/*" "local_data/ohlcv_backup_*/*" \
        ".git/*" "*.pyc" "scripts/*.log"
   ```
6. **`.env` policy**: ship `.env` but rewrite `COINGECKO_API_KEY` as a placeholder; the README tells the new machine to rotate the key.
7. **Dependencies**: `requirements.txt` adds `yfinance==0.2.40` (the user decided to package this item).

### History-extension architecture (item 11)

- `.env` set `HISTORY_DAYS=2326` (today 2026-05-14 back to 2020-01-01).
- Not a full re-pull — **APPEND-EXTEND** strategy:
  ```python
  def run_history_extension(target_start_date="2020-01-01"):
      for cg_id in store.list_ohlcv_ids():
          existing = store.read_ohlcv(cg_id)
          existing_start = existing['date'].min()
          if existing_start <= target_start_date:
              continue
          # pull target_start_date → existing_start - 1day via CCXT waterfall
          new_rows, tier_used = exchange_client.fetch_ohlcv_waterfall(...)
          if new_rows is None:
              new_rows = coingecko_client.fetch_close_price_history(...)  # Tier 4
          snapshot_ohlcv_backup(cg_id)  # safe rollback
          store.append_ohlcv(cg_id, new_rows)  # dedup-by-date
          write_data_coverage_entry(cg_id, tier_used)
  ```
- Estimated total runtime: 200 tokens × ~800 new bars/token on average = ~6–10 minutes.
- Disk: 9.5 MB → ~20 MB of OHLCV (acceptable).
- **scores_history is not back-filled**: keeps the current 2023-06 starting point; the 3y window will be naturally satisfied in 2026-06.

### Incremental-write mechanism (per user item 10 requirement)

Already implemented: `backend/data/local_store.py:150-187` `append_ohlcv` uses `pd.concat` + `drop_duplicates(subset=['date'], keep='last')` + atomic rename. Phase 2 only needs to extend this to stocks. After `yfinance_client.fetch_ohlcv` returns a DataFrame, it goes through the same `store.append_ohlcv` path — zero additional architecture.

---

## 3.3 Artist / aesthetician view

### Light-mode palette (item 3 + Q3 "TradingView white premium feel")

**21 light-mode CSS variables** (already audited for WCAG AA contrast):

```css
html[data-theme="light"] {
    /* Two-layer off-white (user Q3 decision) */
    --bg-primary:    #F0F3FA;  /* canvas pale blue-grey */
    --bg-secondary:  #FFFFFF;  /* card pure white */
    --bg-tertiary:   #F7F8FA;  /* input/button rest */
    --bg-elevated:   #E0E3EB;  /* hover */

    /* Text (near-black rather than #000 — softer) */
    --text-primary:   #131722;  /* AA 16:1 on white */
    --text-secondary: #50565E;
    --text-muted:     #9098A4;

    /* Accent — darkened to satisfy AA contrast on white */
    --accent-green:  #089981;  /* TV light buy — was #26a69a, too light on white */
    --accent-red:    #F23645;
    --accent-blue:   #2962FF;
    --accent-yellow: #B8860B;  /* dark gold — #f7c948 unreadable on white */
    --accent-purple: #9C27B0;

    /* Borders */
    --border-primary: #D6DCE5;
    --border-subtle:  #E8ECF2;

    /* Chart-specific */
    --chart-candle-up:    #089981;
    --chart-candle-down:  #F23645;
    --chart-volume:       #B0B6C0;
    --chart-volume-spike: #B8860B;
    --chart-ma-fast:      #1565C0;
    --chart-ma-slow:      #EF6C00;
    --chart-bb-fill:      rgba(33, 150, 243, 0.07);
}
```

**Theme-toggle mechanism**:
- `<html data-theme="dark" | "light">` attribute; CSS uses `html[data-theme="light"] { ... }`.
- An inline `<script>` at the very top of `<head>` (before the stylesheet loads) resolves localStorage → `prefers-color-scheme` → fallback `"dark"`, **avoiding flash-of-wrong-theme**.
- Listen to `matchMedia('change')`, but only respond when there is no value in localStorage.
- Toggle button: 32×32 icon-only ghost button, placed to the left of Refresh.
- Two SVGs (sun + moon); CSS controls which one shows — "display destination state" (dark mode shows the sun = "switch to light").
- 200 ms cross-fade transition: `transition: background-color 200ms ease, color 200ms ease`.

**Charts re-tint without rebuild (preserve zoom state)**:
- Each chart module adds a `readPalette()` helper that reads CSS variables.
- Add a public `retint()` method that calls `chart.applyOptions(...)` plus each `series.applyOptions(...)`.
- On theme toggle, `app.js` invokes `Candle.retint()` + `IndicatorPanels.retint(family)` ×12.
- SVG modules (score_gauge / sparkline) cache `__lastValue` and re-render.

### Overall hero-panel design (item 9 + Q4 + Q7)

**Strategy A (chosen by the user in Q4)**:

```
┌──────────────────────────────────────────────────────┐
│  OVERALL · COMPOSITE   [?]    Rank 12 / 200          │
│                                                       │
│  ╭───────────╮   76.2       ▲ MACD Histogram +0.74  │
│  │ 240px     │   Composite  ▲ MA50 Slope    +0.61   │
│  │ gauge     │   Score      ▼ RSI Turn      -0.21   │
│  │ (40% bigger)│             "Strong trend setup"   │
│  ╰───────────╯                                       │
│                                                       │
│  Trend          72 × 0.40 = 28.8                     │
│  Reversal       41 × 0.25 = 10.3                     │
│  Signal Breadth 67 × 0.15 = 10.1                     │
│  Risk (low vol) 55 × 0.10 =  5.5                     │
│  Trend TS 2y    83 × 0.05 =  4.2                     │
│  Reversal TS 2y 58 × 0.05 =  2.9                     │
│  ───────────────────────────────                     │
│  Overall                     61.8                    │
└──────────────────────────────────────────────────────┘
┌──────────────────────┐  ┌──────────────────────┐
│ TREND   72.0  Rank 18│  │ REVERSAL  41.0  Rank85│
│ ╭──gauge──╮          │  │ ╭──gauge──╮           │
│ ╰─────────╯          │  │ ╰─────────╯           │
│ 9 components rows    │  │ 7 components rows     │
└──────────────────────┘  └──────────────────────┘
```

**Visual-hierarchy stack (subtle to bold)**:
1. **Document order + full width**: the weakest yet most effective signal.
2. **2 px `--accent-blue` left-side accent border**: doesn't steal the show.
3. **`COMPOSITE` 9 px uppercase pill**: explicitly says "this is composed".
4. **240 px gauge + 56 px score**: size is hierarchy.
5. **Rank chip in the title bar**: every card has one — unified visual language.

**Blurb 4-quadrant text**:
- Trend ≥ 66 AND Reversal < 33: "Strong bull setup"
- Trend < 33 AND Reversal ≥ 66: "Oversold rebound candidate"
- Trend ≥ 66 AND Reversal ≥ 66: "Conflicted — bullish trend with oversold reversal"
- Trend < 33 AND Reversal < 33: "Weak across the board"
- else: "Mixed signals"

### 16 English-label translation table (item 4 + Q11)

**Note: this translation table fixes a Phase-1 leftover collision bug** — in the original, `ma50_dev` (Trend) and `ma50_dev_z_40` (Reversal) were both translated as "MA50 偏离", which users could not distinguish. The English version differentiates them as "MA50 Deviation" and "MA50 Deviation Z (40)".

| Key (unchanged) | Current zh | EN translation |
|---|---|---|
| `mom_ret_10d` | 动量 10d | **Momentum (10d)** |
| `mom_ret_20d` | 动量 20d | **Momentum (20d)** |
| `macd_hist_12_26_9` | MACD 柱 | **MACD Histogram** |
| `macd_hist_slope5_12_26_9` | MACD 斜率 | **MACD Histogram Slope (5d)** |
| `sma_cross_strength_signed_5_20` | SMA 金叉 | **SMA Cross Strength (5/20)** |
| `ema_cross_strength_signed_5_20` | EMA 金叉 | **EMA Cross Strength (5/20)** |
| `ma50_slope_20d` | MA50 斜率 | **MA50 Slope (20d)** |
| `ma50_dev` | MA50 偏离 | **MA50 Deviation** |
| `bb_pctb_20` | 布林位置 | **Bollinger %B (20)** |
| `rsi_dist_os_14` | RSI 超卖 | **RSI Oversold Distance (14)** |
| `rsi_turn_event_14` | RSI 反转事件 | **RSI Turn Event (14)** |
| `kdj_os_distance` | KDJ 超卖 | **KDJ Oversold Distance** |
| `bb_z_20` | 布林 Z(取反) | **Bollinger Z-Score (inverted, 20)** |
| `mr_z_40_skip16` | 均值回归 | **Mean Reversion Z (40, skip 16)** |
| `ma50_dev_z_40` | MA50 偏离 | **MA50 Deviation Z (40)** |
| `mom_ret_5d` | 负动量 5d | **Negative Momentum (5d)** |

### Full tooltip-enrichment table (item 8 + Q2)

**12 panel-header tooltips (native `title`)**:

| Panel | Tooltip |
|---|---|
| SMA Cross (5/20) | Simple Moving Average crossover. When the fast SMA crosses above the slow SMA, momentum is shifting upward (golden cross); a downside cross marks a death cross. |
| MACD (12,26,9) | Moving Average Convergence/Divergence. Histogram = (fast EMA − slow EMA) − signal EMA. Positive and rising = bullish acceleration; falling toward zero = momentum cooling. |
| RSI (14) | Relative Strength Index. 0–100 scale using Wilder smoothing of average gains vs losses. Readings <30 historically mark oversold conditions, >70 overbought. |
| Bollinger (20, 2σ) | Price envelope of mean ± 2 standard deviations over 20 bars. %B near 1 = near upper band (stretched); near 0 = near lower band (mean-reversion candidate). |
| Volume Spike (14) | Ratio of today's volume to its 14-day moving average. Values ≥2× often accompany breakouts or capitulation; volume-confirmed moves tend to follow through. |
| Momentum (5/10/20/30d) | Log returns over four lookbacks. Cross-sectionally ranked. Aligned positive readings across timeframes = persistent uptrend; mixed signs = chop. |
| EMA Cross (5/20) | Exponential Moving Average crossover. EMAs weight recent prices more heavily than SMAs, so the cross fires earlier — sometimes too early in choppy regimes. |
| RSI Mean Reversion (14) | Distance from RSI 30 (oversold). Positive when RSI <30; zero otherwise. Standalone reversal signal — best confirmed by a turn event or %B re-entry. |
| KDJ (9,3,3) | Stochastic K/D/J lines. K below 20 and turning up = oversold reversal candidate; J line amplifies K to surface extremes earlier. |
| Mean Reversion (40, skip 16) | Z-score of price vs its trailing 40-day mean, skipping the most recent 16 days to avoid contaminating with the same window we're trading. Negative = below mean. |
| Z-Score vs MA50 | Standardized distance of price from its 50-day moving average. ±2σ historically marks stretched conditions worth watching for snapbacks. |
| Price Appreciation (10d/20d) | Raw price change percentages over two lookbacks. Provides absolute-return context alongside the cross-sectionally ranked momentum signal. |

**16 Score-Breakdown component-row tooltips (popover)**:

| Row label | Tooltip |
|---|---|
| Momentum (10d) | 10-day log return, ranked cross-sectionally to 0–100 within today's universe. Higher = stronger recent uptrend vs peers. |
| Momentum (20d) | 20-day log return, cross-sectionally ranked. Confirms whether the 10d move is a continuation or a one-off pop. |
| MACD Histogram | MACD(12,26,9) histogram value, cross-sectionally ranked. Positive and growing = bullish acceleration. |
| MACD Histogram Slope (5d) | Slope of the MACD histogram over the last 5 bars. Captures acceleration of acceleration — turns sign before the histogram itself does. |
| SMA Cross Strength (5/20) | Signed normalized gap between fast and slow SMA. Positive = fast above slow (golden-cross regime); magnitude scales the rank. |
| EMA Cross Strength (5/20) | Same as SMA cross but with EMAs — reacts faster to recent prices. |
| MA50 Slope (20d) | Slope of the 50-day moving average over the last 20 days. Positive = the medium-term trend is curving upward. |
| MA50 Deviation | Percentage distance of price above its 50-day MA. Positive in uptrends; very high can presage exhaustion. |
| Bollinger %B (20) | Where price sits within its 20-day Bollinger band. 1.0 = upper band, 0.5 = mean, 0.0 = lower band. |
| RSI Oversold Distance (14) | How far RSI is below the 30 oversold threshold. Larger = more deeply oversold = stronger reversal-candidate. |
| RSI Turn Event (14) | Captures the moment RSI re-crosses 30 from below. Discrete bullish reversal trigger. |
| KDJ Oversold Distance | Stochastic K distance below 20. Larger = more oversold on a higher-volatility-aware scale than RSI. |
| Bollinger Z-Score (inverted, 20) | Standardized %B with sign flipped so that "near lower band" produces a high reversal score. |
| Mean Reversion Z (40, skip 16) | Z-score of price vs its trailing 40-day mean, skipping the most recent 16 days to avoid lookback contamination. Very negative = stretched below mean. |
| MA50 Deviation Z (40) | Z-score of the MA50 deviation series over a 40-day window. Detects when "% above MA50" is itself stretched. |
| Negative Momentum (5d) | Inverted 5-day return. High values indicate recent weakness, which the reversal model treats as a setup for a snapback. |

**Overall info-mark tooltip**:
> Composite of Trend and Reversal weighted by finance-theory priors: 40% Trend + 25% Reversal + 15% signal breadth + 10% risk-adjustment + 10% 2y historical strength. Cross-sectionally ranked to 0-100.

**7 parameter-label tooltips (native `title`)**:

| Label | Tooltip |
|---|---|
| period | Lookback window in bars (days). |
| fast / slow | Number of bars used in the faster/slower moving average. Smaller fast = more sensitive but more whipsaws. |
| signal | Smoothing window applied to MACD line to compute the signal line. |
| N | KDJ: stochastic window. |
| M1 | KDJ: K-line smoothing factor. |
| M2 | KDJ: D-line smoothing factor. |
| std | Number of standard deviations for the Bollinger band width. |
| window / ma_window | Number of bars in the volume moving average baseline. |

---

# Part 4 — Detailed Specs for the 11 Items (with file:line touchpoints + acceptance)

> This part unfolds the why / what / where / how / acceptance for every item. Each item follows this template:
>
> ```
> ### R8-N · user item X
> **User verbatim**: ...
> **why**: ...
> **what**: list of changes
> **where**: file + line numbers
> **how**: implementation key points
> **acceptance**: item-by-item verifiable acceptance criteria
> ```

## Phase 2A — Infrastructure + Data Expansion (Week 1)

### R8-1A · user item 10 (green-folder + incremental + corruption recovery)

**User verbatim**: *"The vast majority of the data should be stored in local folders... first back up the data locally, then update with incremental writes... otherwise once the database is corrupted, robustness will be very poor."*

**why**: Plan agent B found that `backend/main.py:57` ignores `DATA_DIR`, which is the P0 blocker for "green-folder"; there is no boot-time integrity check; there is no per-token repair path.

**what**:
1. Fix the portability bug.
2. Add boot-time integrity verification.
3. Add a single-token repair mechanism.
4. Add a packaging script.

**where + how**:

- `backend/main.py:57`: change `LocalStore(Path(PROJECT_ROOT) / "local_data")` to `LocalStore(DATA_DIR)` (`DATA_DIR` is already resolved to a relative/absolute path in `config.py:74-79`).

- New file `backend/data/integrity.py`:
  ```python
  def verify_local_data_integrity(store, validator) -> dict:
      """boot-time check, returns per-token issue list"""
      issues = []
      for cg_id in store.list_ohlcv_ids():
          path = OHLCV_DIR / f"{cg_id}.csv"
          # 1. file size > 0
          if path.stat().st_size == 0:
              issues.append((cg_id, "empty_file"))
              continue
          # 2. header equals OHLCV_COLUMNS
          # 3. pd.read_csv succeeds
          # 4. row count >= MIN_OHLCV_ROWS
          # 5. last_date within 14 days for active tokens
          # 6. validate_ohlcv issues empty
          ...
      return issues
  ```

- New directory `local_data/quarantine/`: corrupt CSVs are moved here (`shutil.move`), not deleted.

- `backend/data/fetcher.py` new method `repair_token(cg_id)`: calls `fetch_ohlcv_waterfall` + `fetch_close_price_history` to re-pull a single token, then writes atomically.

- New route `backend/api/routes_admin.py` `POST /api/admin/repair/{id}`: localhost-only check (`request.client.host == "127.0.0.1"`).

- `backend/main.py` lifespan: on boot call `verify_local_data_integrity`, log the issues but **do not auto-repair** (to avoid an .env mistake triggering 200 API calls).

- New script `scripts/pack_green_folder.sh`:
  ```bash
  #!/bin/bash
  set -e
  cd "$(dirname "$0")/.."
  out="dashboard_green_$(date +%Y%m%d).zip"
  cp .env .env.bak
  sed -i.tmp 's/^COINGECKO_API_KEY=.*/COINGECKO_API_KEY=your-coingecko-pro-key-here/' .env
  zip -r "$out" . \
    -x "venv/*" "*/__pycache__/*" "local_data/ohlcv_backup_*/*" \
       ".git/*" "*.pyc" "scripts/*.log" "*.tmp"
  mv .env.bak .env
  rm -f .env.tmp
  echo "Wrote $out ($(du -h $out | cut -f1))"
  ```

- `README.md` add a "porting to another machine" section.

**acceptance**:
- [ ] Set `.env` `DATA_DIR=/tmp/test_dash`; both fetcher writes and API reads happen under `/tmp/test_dash`.
- [ ] After `echo "garbage" > local_data/ohlcv/bitcoin.csv`, boot logs that file as quarantined.
- [ ] `curl -X POST http://127.0.0.1:8080/api/admin/repair/bitcoin` succeeds in repairing the single token.
- [ ] `curl -X POST http://example.com/api/admin/repair/bitcoin` is rejected (not 127.0.0.1).
- [ ] `bash scripts/pack_green_folder.sh` produces `dashboard_green_YYYYMMDD.zip`; unzipping on a new machine, `setup.sh && run.sh` is enough.
- [ ] `local_data/metadata/data_integrity_log.json` is updated on every boot.

---

### R8-1B · user item 11 (OHLCV history extended back to 2020-01-01)

**User verbatim**: *"The data must reach back to 2020-01-01. For tokens launched after 2020, start from the listing day; for stocks or tokens that existed before 2020 we must reach 2020-01-01."*

**why**: in Phase 1 all 200 CSVs have earliest date 2023-05-15 (HISTORY_DAYS=1095). The user wants an old token like BTC to reach 2020-01-01.

**what**:
1. Expand CCXT to 8 exchanges ("exhaustive" fetching).
2. Add a `run_history_extension` method to append-prepend.
3. Write per-token `data_coverage.json` metadata.
4. New endpoint exposing coverage.

**where + how**:

- `.env`: `HISTORY_DAYS=2326`.
- `backend/data/exchange_client.py`:
  - `EXCHANGE_PRIORITY` extended to 8 exchanges: `["binance", "okx", "bybit", "gateio", "coinbase", "kraken", "kucoin", "bitstamp"]`.
  - `PER_CALL_LIMIT` dict adds Coinbase=300, Kraken=720, KuCoin=1500, Bitstamp=1000.
  - Pagination via `since=` cursor already supports the 4000-day cap — no structural change.
- New methods in `backend/data/fetcher.py`:
  ```python
  def run_history_extension(self, target_start_date="2020-01-01") -> dict:
      """For each existing token, prepend OHLCV back to target_start_date.
      Returns summary with extended_tokens / tier_used / failed."""
      from datetime import datetime, timedelta
      summary = {"extended": 0, "skipped": 0, "failed": [], "tier_breakdown": {}}
      target_dt = datetime.strptime(target_start_date, "%Y-%m-%d")
      for cg_id in self.store.list_ohlcv_ids():
          existing = self.store.read_ohlcv(cg_id)
          if existing is None or len(existing) == 0:
              continue
          existing_start = existing['date'].min()
          if existing_start <= target_dt:
              summary["skipped"] += 1
              continue
          # snapshot before mutation
          self.store.snapshot_ohlcv_backup(cg_id)
          # Tier 1: CCXT waterfall (8 exchanges)
          new_df, source = self.exchange_client.fetch_ohlcv_waterfall(
              cg_id=cg_id,
              days=(existing_start - target_dt).days,
              mapper=self.mapper,
              end_date=existing_start - timedelta(days=1),
          )
          tier = 1
          if new_df is None or new_df.empty:
              # Tier 4: CG close-only
              new_df = self.coingecko_client.fetch_close_price_history(
                  cg_id=cg_id,
                  from_date=target_dt,
                  to_date=existing_start - timedelta(days=1),
              )
              if new_df is not None and not new_df.empty:
                  new_df = _coingecko_close_to_ohlcv(new_df)
                  new_df["source"] = COINGECKO_SOURCE_TAG
                  source = "coingecko"
                  tier = 4
          if new_df is not None and not new_df.empty:
              self.store.append_ohlcv(cg_id, new_df)
              summary["extended"] += 1
              summary["tier_breakdown"].setdefault(tier, []).append(cg_id)
              self._update_data_coverage(cg_id, source=source, tier=tier)
          else:
              summary["failed"].append(cg_id)
      return summary
  ```
- New file `local_data/metadata/data_coverage.json` (schema in Part 3.2).
- New route `backend/api/routes_market.py` (shared with R8-2A) `GET /api/data-coverage/{cg_id}`.
- `scores_history.csv` is **not back-filled**: it keeps its 2023-06 starting point (Plan B recommendation; the 2y window is already satisfied, and the 3y window will be naturally satisfied in 2026-06).
- New script `scripts/run_history_extension.py` to run once.
- **Default candle chart shows the entire history** (2026-05-15 revision): `frontend/js/app.js renderCandle` becomes `getOhlc(id, 2326)` to pull the full 2020→today range; `timeScale().fitContent()` expands the view. `renderAllIndicators` is correspondingly changed to `days=2326` so that the time axis stays aligned. The original "default 1 year" constraint has been cancelled (direct user instruction).

**acceptance**:
- [ ] BTC `local_data/ohlcv/bitcoin.csv` first row `date <= 2020-01-01` (in practice it should be OKX data from ~2017).
- [ ] SOL `local_data/ohlcv/solana.csv` first row `date >= 2020-04-XX` (its OKX listing date).
- [ ] SUI `local_data/ohlcv/sui.csv` first row `date >= 2023-05-XX` (its listing date — for tokens listed post-2023, keep their listing day as the start).
- [ ] `data_coverage.json` has a `tier_breakdown` array for every token.
- [ ] `GET /api/data-coverage/bitcoin` returns 200 with the `tier_breakdown`.
- [ ] `scores_history.csv` row count is unchanged (no back-fill).
- [ ] Default candle chart at a 1440 viewport shows the entire history (fitContent expands 2020→today).
- [ ] Total runtime ≤ 15 minutes (one-off history-extension job).

---

### R8-1C · user item 5 (market cap + liquidity + 30d avg volume panel)

**User verbatim**: *"Add a panel for inspecting the token's real-time quote: (a) market-cap ranking and the absolute market cap; (b) liquidity data; (c) 30-day average volume."*

**why**: Phase-1 `top200_current.csv` only has 5 columns — missing `mcap_rank` / `total_volume` / liquidity proxy. The CG `/coins/markets` endpoint already returns those, but Phase 1 didn't parse them.

**what**:
1. Extend the CG field-extraction set.
2. Upgrade the `top200_current` schema.
3. New endpoint `/api/market_overview/{id}`.
4. New market panel on the front end.

**where + how**:

- `backend/data/coingecko_client.py:276-290`: extend the `expected` field list:
  ```python
  expected = [
      "id", "symbol", "name", "current_price", "market_cap",
      # New columns
      "market_cap_rank", "fully_diluted_valuation", "total_volume",
      "circulating_supply", "total_supply", "max_supply",
      "price_change_percentage_24h",
  ]
  ```
- `backend/data/data_validator.py:27-33`: extend `TOP200_REQUIRED_COLUMNS` to add `market_cap_rank` + `total_volume`.
- New method `DataService.avg_volume_30d(cg_id) -> Optional[float]`:
  ```python
  def avg_volume_30d(self, cg_id: str) -> Optional[float]:
      df = self.get_ohlcv(cg_id)
      if df is None or len(df) == 0:
          return None
      tail = df.tail(30)
      # if majority source=coingecko, vol is fake (zero-filled), return None
      if "source" in tail.columns:
          fallback_pct = (tail["source"] == "coingecko").mean()
          if fallback_pct >= 0.5:
              return None
      return float(tail["volume"].mean())
  ```
- New router `backend/api/routes_market.py`:
  ```python
  @router.get("/api/market_overview/{cg_id}")
  def market_overview(cg_id: str):
      cg_id = validate_cg_id(cg_id)
      svc = get_service()
      token = svc.get_token(cg_id)
      if token is None:
          raise HTTPException(404, f"unknown token {cg_id}")
      df = svc.get_ohlcv(cg_id)
      source = str(df['source'].iloc[-1]) if df is not None else None
      pair = svc.get_symbol_mapping(cg_id, source) if source else None
      return {
          "cg_id": cg_id,
          "market_cap": token.get("mcap"),
          "market_cap_rank": token.get("market_cap_rank"),
          "fully_diluted_valuation": token.get("fdv"),
          "current_price": token.get("price"),
          "price_change_24h_pct": token.get("price_change_percentage_24h"),
          "total_volume_24h": token.get("total_volume"),
          "avg_volume_30d": svc.avg_volume_30d(cg_id),
          "circulating_supply": token.get("circulating_supply"),
          "total_supply": token.get("total_supply"),
          "liquidity": {
              "exchange": source,
              "spot_pair": pair,
              "source_tag": source,
          }
      }
  ```
- Front-end `frontend/index.html` inserts between token-selector and score-detail:
  ```html
  <section id="market-cap-panel" class="market-panel">
    <div class="market-tile" data-field="market_cap_rank">
      <div class="market-tile-label">Mcap Rank</div>
      <div class="market-tile-value" id="mcap-rank">#--</div>
    </div>
    <div class="market-tile" data-field="market_cap">
      <div class="market-tile-label">Market Cap</div>
      <div class="market-tile-value" id="mcap-value">$--</div>
    </div>
    <div class="market-tile" data-field="total_volume_24h">
      <div class="market-tile-label">24h Volume</div>
      <div class="market-tile-value" id="vol-24h">$--</div>
    </div>
    <div class="market-tile" data-field="avg_volume_30d">
      <div class="market-tile-label">30d Avg Volume</div>
      <div class="market-tile-value" id="vol-30d">$--</div>
    </div>
    <div class="market-tile" data-field="liquidity">
      <div class="market-tile-label">Liquidity</div>
      <div class="market-tile-value" id="liquidity-source">--</div>
    </div>
  </section>
  ```
- New component `frontend/js/components/market_panel.js` (~50 lines): calls `/api/market_overview/{id}` and renders tiles, formatting with `Intl.NumberFormat` ($1.42T / $79K / 2.85B etc.).
- New CSS rules in `styles.css` for `.market-panel` + `.market-tile`.
- `frontend/js/api.js` adds a `getMarketOverview(id)` method.
- `frontend/js/app.js` selectToken flow adds `await MarketPanel.render(id)`.

**acceptance**:
- [ ] `top200_current.csv` has at least 12 columns.
- [ ] `GET /api/market_overview/bitcoin` returns 8 numeric fields, none null.
- [ ] For a CG-fallback token (e.g. zano), `avg_volume_30d=null` and the UI shows "—".
- [ ] On the BTC page the front end shows 5 tiles with reasonable values.
- [ ] Tile hover shows tooltip ("Liquidity: data from binance via BTC/USDT pair").

---

### R8-1D · user item 7 (40 US-stock integration)

**User verbatim**: *"The system currently only supports two stocks; we need to expand the count … research relevant information for these stocks via Yahoo Finance"* + 40-ticker list + Q5 "default = CRCL" + Q6 "fully separated".

**40-ticker list**:
```
ANY, APLD, ARBK, BIGG, BITF, BKKT, BLSH, BTBT, BTCS, BTDR,
BTGO, BTM, CAN, CIFR, CLSK, COIN, CORZ, CRCL, DEFT, DMGGF,
EBON, ETOR, EXOD, FIGR, FLD, GEMI, GLXY, GREE, HIVE, HOOD,
HUT, IREN, MARA, MOGO, MSTR, NPPTF, RIOT, SMLR, VOYG, WULF
```

**why**: Phase 1 had no stocks integration at all. The yfinance Python lib is the standard choice; US tickers do not need a suffix.

**what**:
1. New `yfinance_client` module.
2. Universe-config file.
3. The `asset_class` dimension propagates through the backend API + front end.
4. Front-end tab strip.
5. An independent stocks daily-refresh job.

**where + how**:

- `requirements.txt` adds `yfinance==0.2.40`.
- New file `local_data/metadata/stocks_universe.csv`:
  ```csv
  ticker,asset_class,name,exchange,region,active
  ANY,us-stock,Sphere 3D Corp,NASDAQ,US,true
  APLD,us-stock,Applied Digital Corp,NASDAQ,US,true
  ARBK,us-stock,Argo Blockchain plc,NASDAQ,US,true
  ... (40 rows)
  ```
  (The `name` field can be auto-filled from `yfinance Ticker.info["longName"]` — enrich on the first start.)
- New file `backend/data/yfinance_client.py`:
  ```python
  import yfinance as yf
  import pandas as pd
  from typing import Optional
  from datetime import date

  STOCKS_SOURCE_TAG = "yfinance"

  class YFinanceClient:
      def __init__(self):
          self._tk_cache = {}

      def _ticker(self, sym):
          if sym not in self._tk_cache:
              self._tk_cache[sym] = yf.Ticker(sym)
          return self._tk_cache[sym]

      def fetch_ohlcv(self, ticker: str, start: date, end: date) -> Optional[pd.DataFrame]:
          t = self._ticker(ticker)
          df = t.history(start=str(start), end=str(end),
                         auto_adjust=True, actions=False, prepost=False)
          if df is None or df.empty:
              return None
          df = df.rename(columns={
              "Open": "open", "High": "high", "Low": "low",
              "Close": "close", "Volume": "volume"
          })
          df.index = df.index.tz_localize(None).normalize()
          df["date"] = df.index
          df["source"] = STOCKS_SOURCE_TAG
          df = df.reset_index(drop=True)
          return df[["date", "open", "high", "low", "close", "volume", "source"]]

      def fetch_market_overview(self, ticker: str) -> dict:
          info = self._ticker(ticker).info
          return {
              "ticker": ticker,
              "name": info.get("longName"),
              "exchange": info.get("exchange"),
              "market_cap": info.get("marketCap"),
              "shares_outstanding": info.get("sharesOutstanding"),
              "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
              "total_volume_24h": info.get("regularMarketVolume"),
              "price_change_percentage_24h": info.get("regularMarketChangePercent"),
          }
  ```
- New `backend/data/fetcher.py` method `run_stocks_daily_update`: mirrors the crypto path but with its own try/finally + `last_update.json` section.
- `backend/main.py` lifespan: APScheduler gets a second cron at 08:35 Asia/Shanghai for stocks.
- `backend/services/data_service.py:99-152` `list_tokens()` refactor:
  ```python
  def list_tokens(self) -> List[Dict]:
      out = []
      # crypto tokens
      for cg_id in self._list_crypto_ohlcv_ids():
          out.append({**meta, "asset_class": "crypto", "id": cg_id})
      # us stocks
      for ticker in self._list_stocks_universe(asset_class="us-stock"):
          out.append({**meta, "asset_class": "us-stock", "id": ticker})
      return out
  ```
- `backend/scoring/ranking.py` adds `asset_class` partitioning:
  ```python
  def cross_sectional_percentile(scores: Dict[str, float],
                                  asset_class: Optional[str] = None,
                                  tokens_by_class: Optional[Dict[str, str]] = None) -> Dict[str, float]:
      if asset_class is None or tokens_by_class is None:
          # legacy: rank all together
          ...
      else:
          # partition by class, rank within each
          ...
  ```
- `backend/api/_validators.py:26` `validate_cg_id` regex extended: `^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,63}$` (allow uppercase + dot for `.HK`, still reject `..` / `/` / leading dot).
- `backend/api/routes_scores.py` `all_scores()` adds `asset_class: Optional[str] = None` query param; filter then cross-section rank.
- Front-end `frontend/index.html` adds above the sidebar:
  ```html
  <div class="sidebar-tabs">
    <button class="tab-btn active" data-tab="crypto">Crypto (200)</button>
    <button class="tab-btn" data-tab="us-stock">US Stocks (40)</button>
  </div>
  ```
- Front-end `frontend/js/app.js` adds tab logic: tab state is stored in `location.hash`; on tab switch, reload the rankings + change the default token: crypto→BTC, us-stock→CRCL.
- The token-selector dropdown is filtered by candidates of the active tab.

**acceptance**:
- [ ] Files like `local_data/ohlcv/COIN.csv`, `MSTR.csv` — 40 in total — exist, `source=yfinance`, row count ≥ 250.
- [ ] `local_data/metadata/stocks_universe.csv` has 40 rows.
- [ ] `GET /api/tokens` returns 240 entries (200 + 40), each containing `asset_class`.
- [ ] `GET /api/scores?asset_class=us-stock` only returns the 40 US stocks, ranked cross-sectionally on their own.
- [ ] The crypto rank-1 token is not the stocks rank-1 (fully separated).
- [ ] The front-end sidebar shows 2 tabs; switching to US Stocks selects CRCL by default; the hash becomes `#tab=us-stock`.
- [ ] Stocks fetch on a weekend does not error (yfinance skips non-trading days).
- [ ] The stocks daily cron fires at 08:35, independent of the crypto cron.

---

### Phase 2A acceptance: R8-α audit round

When complete, dispatch **2 fresh-context agents**:
- **Agent A**: System Architect — verifies portability, history extension, stocks integration.
- **Agent B**: Data Scientist — verifies data completeness, independent cross-section ranking, and that the 4-tier waterfall is actually exercised.

Each agent gets a port: 8091 (A), 8092 (B). Reports go to `/tmp/AUDIT_R8a_*.md`.

---

## Phase 2B — Scoring System + Indicator Robustness (Week 2)

### R8-2A · user item 2A (Tier A composite score)

**User verbatim**: item 2 (a-c) + item 9 "should be placed at the top" + Q1 "do both A and B" + Q4 Strategy A + Q7 "6 sleeves".

**why**: the two Trend / Reversal numbers leave users at a loss; we need one headline number.

**what**: see Part 3.1 for details.

**where + how**:

- New indicator family `backend/indicators/volatility.py`:
  ```python
  class VolatilityFamily(IndicatorFamily):
      name = "volatility"
      default_params = {"windows": [20, 60]}

      def compute(self, df, **params):
          p = self.merged_params(params)
          windows = p["windows"]
          close = df["close"].astype(float)
          log_ret = np.log(close / close.shift(1))
          out = {}
          for w in windows:
              # annualised (365 trading days for crypto)
              out[f"vol_{w}d"] = log_ret.rolling(w).std() * np.sqrt(365)
          return out
  ```
- `backend/indicators/registry.py:29-42` registers `volatility`.
- New module `backend/scoring/overall_score.py`:
  ```python
  TIER_A_WEIGHTS = {
      "trend": 0.40,
      "reversal": 0.25,
      "breadth": 0.15,
      "risk": 0.10,
      "ts_trend_2y": 0.05,
      "ts_reversal_2y": 0.05,
  }

  def compute_breadth(trend_components: dict) -> float:
      """% of 9 trend signals that are positive."""
      pos = sum(1 for v in trend_components.values() if v is not None and v > 0)
      return 100.0 * pos / len(trend_components) if trend_components else 0.0

  def compute_overall_score(
      trend_cs_pct: float, reversal_cs_pct: float,
      breadth: float, risk_cs_pct: float,
      ts_trend_2y_pct: Optional[float], ts_rev_2y_pct: Optional[float],
      weights: dict = TIER_A_WEIGHTS,
  ) -> float:
      ts_trend = ts_trend_2y_pct if ts_trend_2y_pct is not None else 50.0
      ts_rev = ts_rev_2y_pct if ts_rev_2y_pct is not None else 50.0
      return (
          weights["trend"]       * trend_cs_pct
        + weights["reversal"]    * reversal_cs_pct
        + weights["breadth"]     * breadth
        + weights["risk"]        * risk_cs_pct
        + weights["ts_trend_2y"] * ts_trend
        + weights["ts_reversal_2y"] * ts_rev
      )

  def cross_sectional_overall_scores(all_indicators, all_scores, vol_data, asset_class=None) -> Dict[str, float]:
      ...

  def compute_overall_components(token_id, all_indicators, all_scores, weights) -> dict:
      """Returns 6 sleeve rows with raw value + weight + contribution."""
      ...
  ```
- Modify `backend/services/data_service.py:262-287` `current_scores()` to add:
  ```python
  out[cg_id] = {
      ...existing fields...,
      "overall_score": float(overall_scores.get(cg_id, 0.0)),
      "overall_cs_percentile": float(cs_overall.get(cg_id, 0.0)),
      "overall_components": compute_overall_components(cg_id, ...),
  }
  ```
- `backend/api/routes_scores.py` adds the `overall` fields; option `?sort_by=overall`.
- Modify the `scores_history.csv` schema: add `overall_score`, `overall_cs_percentile` columns.
- Read compatibility: `data_service._load_scores_history` `fillna(None)` the overall fields for old rows.
- Front-end `frontend/index.html` refactors `score-detail`:
  ```html
  <section class="score-detail">
    <h2 class="section-header">Score Breakdown</h2>

    <!-- NEW Overall hero card, full width -->
    <div class="score-card score-card-overall">
      <header class="overall-head">
        <h3>Overall <span class="badge-composite">COMPOSITE</span>
          <span class="info-mark" data-explainer="overall">?</span></h3>
        <span class="rank-chip" id="overall-rank">Rank — / —</span>
        <div id="overall-percentiles" class="percentiles muted"></div>
      </header>
      <div class="overall-body">
        <div id="overall-gauge" class="score-gauge score-gauge-xl"></div>
        <div class="overall-meta">
          <div id="overall-value" class="score-large score-xl">--</div>
          <div id="overall-blurb" class="score-blurb muted">--</div>
        </div>
        <ul id="overall-components" class="components components-overall"></ul>
      </div>
    </div>

    <!-- Existing 2-col Trend + Reversal grid -->
    <div class="score-detail-grid">
      <div class="score-card score-card-trend">
        <header>
          <h3>Trend <span class="info-mark" data-explainer="trend">?</span></h3>
          <span class="rank-chip" id="trend-rank">Rank — / —</span>
        </header>
        ... existing trend content ...
      </div>
      <div class="score-card score-card-reversal">
        ... mirror for reversal ...
      </div>
    </div>
  </section>
  ```
- `frontend/js/app.js renderScoreDetail()` is extended to render the overall card.
- `frontend/css/styles.css` adds `.score-card-overall { border-left: 2px solid var(--accent-blue) }`, `.badge-composite { ... 9px uppercase pill }`, `.score-gauge-xl { width: 240px }`, `.score-xl { font-size: 56px }`.

**acceptance**:
- [ ] `GET /api/scores/bitcoin` returns `overall_score`, `overall_cs_percentile`, `overall_components` (all 6 keys present).
- [ ] On a single day across 200 tokens, the `overall_score` ranks uniquely cover 1..200.
- [ ] Walk-forward Spearman ρ(`overall`, forward 5d return) ≥ ρ((trend+reversal)/2, forward 5d return) + 0.02 (last-90-day hold-out using current `scores_history` data).
- [ ] The hero card fits entirely above the fold on a 1440×900 viewport.
- [ ] The gauge is visually ≥ 30% larger than Trend/Reversal (measured from the DOM rect).
- [ ] The sum of the 6 sleeves equals the displayed `overall_score` (mathematical consistency).

---

### R8-2B · user item 6 (indicator-robustness backtest)

**User verbatim**: *"(a) Backtest the key buy/sell points (e.g. golden-cross, death-cross strategies). (b) Evaluate whether trading exactly per the indicator would have been profitable or loss-making historically."*

**why**: the user asks "can I trust this RSI?". The current `golden_cross.py` can only run SMA — it does not generalise to other indicators.

**what**:
1. Refactor `golden_cross.py` to a Strategy pattern.
2. 9 canonical strategies.
3. `universe_robustness` module.
4. `/api/indicator-robustness` endpoint with cache.
5. A UI section.

**where + how**:

- New module `backend/backtest/engine.py`:
  ```python
  @dataclass
  class BacktestResult:
      cagr: float; sharpe: float; max_drawdown: float; n_trades: int
      final_equity: float; win_rate: float; avg_trade_return: float
      equity_curve: list[dict]; params: dict

  def run_backtest(
      df: pd.DataFrame,
      strategy: Callable[[pd.DataFrame, dict], pd.Series],
      strategy_params: dict | None = None,
      start_date: str | None = None,
      commission_bps: float = 5.0,
  ) -> BacktestResult:
      """Generic backtest engine. Strategy returns position [0,1] aligned to df.index."""
      ...
  ```
  Lift the statistical computation from `golden_cross.py:32-139` into here.
- New module `backend/backtest/strategies.py`:
  ```python
  def strategy_rsi_oversold(df, period=14, entry=30, exit=50) -> pd.Series:
      rsi = INDICATORS["rsi"].compute(df, period=period)[f"rsi_{period}"]
      in_pos = pd.Series(0, index=df.index)
      pos = 0
      for i in range(len(df)):
          if pos == 0 and rsi.iloc[i] < entry:
              pos = 1
          elif pos == 1 and rsi.iloc[i] > exit:
              pos = 0
          in_pos.iloc[i] = pos
      return in_pos

  def strategy_macd_signal_cross(df, fast=12, slow=26, signal=9) -> pd.Series:
      ...
  def strategy_kdj_oversold_cross(df, N=9, M1=3, M2=3) -> pd.Series:
      ...
  ... 9 total

  CANONICAL_STRATEGIES = {
      "rsi_oversold_30_50": (strategy_rsi_oversold, {"period": 14, "entry": 30, "exit": 50}),
      "macd_signal_cross": (strategy_macd_signal_cross, {}),
      "kdj_oversold_cross": (strategy_kdj_oversold_cross, {}),
      "bollinger_lower_band": (strategy_bollinger_lower_band, {"period": 20, "num_std": 2.0}),
      "sma_golden_cross": (strategy_sma_golden_cross, {"fast": 5, "slow": 20}),
      "ema_golden_cross": (strategy_ema_golden_cross, {"fast": 5, "slow": 20}),
      "momentum_breakout": (strategy_momentum_breakout, {"lookback": 20, "threshold": 0.0}),
      "zscore_reversion": (strategy_zscore_reversion, {"window": 40, "entry_z": -2.0, "exit_z": 0.0}),
      "price_appreciation": (strategy_price_appreciation, {"lookback": 20, "threshold": 0.10}),
  }
  ```
- New module `backend/backtest/universe_robustness.py`:
  ```python
  def run_universe_robustness(
      svc: DataService,
      strategies: dict = CANONICAL_STRATEGIES,
      asset_class: str = "crypto",
      min_history_days: int = 365,
  ) -> dict:
      results = {}
      for strat_name, (fn, params) in strategies.items():
          per_token = []
          for cg_id in svc.list_active_ids(asset_class=asset_class):
              df = svc.get_ohlcv(cg_id)
              if df is None or len(df) < min_history_days: continue
              result = run_backtest(df, strategy=fn, strategy_params=params)
              per_token.append({
                  "cg_id": cg_id, "symbol": svc.get_token(cg_id)["symbol"],
                  "sharpe": result.sharpe, "cagr": result.cagr,
                  "max_dd": result.max_drawdown, "n_trades": result.n_trades,
                  "win_rate": result.win_rate,
              })
          # Aggregate
          sharpes = [r["sharpe"] for r in per_token if r["sharpe"] is not None]
          median_sharpe = np.median(sharpes)
          pct_positive = sum(1 for s in sharpes if s > 0) / len(sharpes) * 100
          worst = min(per_token, key=lambda r: r["sharpe"])
          best = max(per_token, key=lambda r: r["sharpe"])
          # Reliability badge
          if median_sharpe >= 0.5 and pct_positive >= 60 and worst["sharpe"] >= -1.0:
              reliability = "reliable"
          elif median_sharpe >= 0.2 or pct_positive >= 50:
              reliability = "caveats"
          else:
              reliability = "unreliable"
          results[strat_name] = {
              "median_sharpe": median_sharpe, "mean_sharpe": np.mean(sharpes),
              "pct_positive": pct_positive,
              "worst": {"cg_id": worst["cg_id"], "sharpe": worst["sharpe"]},
              "best": {"cg_id": best["cg_id"], "sharpe": best["sharpe"]},
              "reliability": reliability,
              "n_tokens": len(per_token),
              "per_token": per_token,
          }
      return results
  ```
- Cache `local_data/robustness_cache/`:
  - `robustness_summary.json` — top-level aggregate.
  - `robustness_<strategy_name>.json` — per-token detail.
  - `robustness_meta.json` — `{computed_at, ohlcv_hash, universe_size}`.
- Invalidation: at the end of the daily update, compute the `ohlcv_hash` and compare with the stored hash; if different, recompute in the background.
- New router `backend/api/routes_robustness.py`:
  - `GET /api/indicator-robustness` top-level summary.
  - `GET /api/indicator-robustness/{strategy_name}` detail.
  - `POST /api/indicator-robustness/recompute` manual trigger.
- `backend/backtest/golden_cross.py` degrades to a thin wrapper (keeps `/api/backtest/{cg_id}` unchanged).
- Front-end `frontend/index.html` after the existing `<details class="backtest">` adds:
  ```html
  <section class="indicator-robustness">
    <h2 class="section-header">Indicator Robustness</h2>
    <table id="robustness-table">
      <thead><tr>
        <th>Strategy</th><th>Median Sharpe</th><th>% Positive</th>
        <th>Worst</th><th>Best</th><th>Reliability</th>
      </tr></thead>
      <tbody></tbody>
    </table>
    <div id="robustness-detail" hidden></div>
  </section>
  ```
- `frontend/js/components/robustness_panel.js` (~100 lines) renders the table + on row click expands the distribution.

**acceptance**:
- [ ] `backend/backtest/engine.py` exists; `golden_cross.py` is reduced to ≤ 20 lines.
- [ ] `CANONICAL_STRATEGIES` registers exactly 9.
- [ ] `GET /api/indicator-robustness` returns 200 in <100 ms (cache hit), with all 9 strategies returned.
- [ ] A manual `POST /api/indicator-robustness/recompute` completes within ≤ 5 minutes.
- [ ] Modifying any OHLCV CSV triggers an automatic recompute in the next daily update.
- [ ] The front-end table has 9 rows, each with a reliability badge (reliable/caveats/unreliable).
- [ ] Clicking the RSI row expands the per-token Sharpe distribution.
- [ ] Clicking a token in the distribution jumps to that token's detail page.

---

### R8-2C · user item 1 (score-display optimisation)

**User verbatim**: *"(a) Clarify the specific meaning and strengths of the two scores. (b) Add a comparison dimension showing the current token's rank in the Top 200. (c) Add an explanation of the calculation logic in the charts."*

**what**:
1. Add rank fields to the API.
2. New explainer module + endpoint.
3. Front-end rank chip + popover modal.

**where + how**:

- In `backend/services/data_service.py` `current_scores()` add:
  ```python
  # rank_in_universe by descending score
  trend_rank = {cid: r+1 for r, (cid, _) in enumerate(
      sorted(out.items(), key=lambda x: x[1]['trend_score'], reverse=True)
  )}
  reversal_rank = {cid: r+1 for r, (cid, _) in enumerate(
      sorted(out.items(), key=lambda x: x[1]['reversal_score'], reverse=True)
  )}
  overall_rank = {cid: r+1 for r, (cid, _) in enumerate(
      sorted(out.items(), key=lambda x: x[1]['overall_score'], reverse=True)
  )}
  for cid in out:
      out[cid]['rank_in_universe_trend'] = trend_rank[cid]
      out[cid]['rank_in_universe_reversal'] = reversal_rank[cid]
      out[cid]['rank_in_universe_overall'] = overall_rank[cid]
      out[cid]['universe_size'] = len(out)
  ```
- `backend/api/routes_scores.py:74-115` `token_score()` adds the rank fields to the response.
- New module `backend/scoring/explainers.py` (see Part 3.1 for details).
- New router `backend/api/routes_scoring_meta.py`: `GET /api/scoring/explainer` returns the three explainers.
- Front-end `frontend/index.html` adds `<span class="rank-chip" id="trend-rank">Rank — / —</span>` to each score-card title bar.
- Front-end `frontend/js/app.js` `renderScoreDetail()` writes into the rank chip.
- New popover: clicking `.info-mark[data-explainer]` triggers a modal overlay that renders the markdown.
- `frontend/css/styles.css` adds `.rank-chip { font-variant-numeric: tabular-nums; padding: 1px 6px; border-radius: 3px; ... }`, `.explainer-modal { ... }`.

**acceptance**:
- [ ] `GET /api/scores/bitcoin` includes `rank_in_universe_trend`, `..._reversal`, `..._overall`, `universe_size`.
- [ ] Next to each score-card title the text "Rank N / 200" is visible.
- [ ] Clicking any `.info-mark` pops up a modal containing the phrase "rank-percentile blending".
- [ ] For close-only tokens the rank displays "—" without erroring (the API returns null).

---

### Phase 2B acceptance: R8-β audit round

Dispatch **2 fresh-context agents**:
- **Agent C**: Quant Researcher — verifies Tier A formula numerical correctness, Spearman ρ baseline tests, that the 9 strategies' data are reasonable.
- **Agent D**: Product Designer — verifies hero-panel visuals, accuracy of explainer modal content.

Reports to `/tmp/AUDIT_R8b_*.md`.

---

## Phase 2C — UX Visual (Week 3)

### R8-3A · user item 9 (Overall hero panel UI — already in R8-2A)

Already implemented in R8-2A. This phase mainly handles polish + mobile adaptation.

**Mobile (<768px)** stacking order (top to bottom):
1. Overall card — full width, gauge centered, components folded into `<details>`.
2. Trend card — full width.
3. Reversal card — full width.

### R8-3B · user item 3 (light mode)

**what + how**: see Part 3.3 for details.

**Implementation checklist**:

- [ ] `frontend/css/styles.css` adds the `html[data-theme="light"] { ... }` block overriding all 21 CSS variables.
- [ ] `frontend/index.html` adds an inline `<script>` at the top of `<head>` to resolve localStorage + prefers-color-scheme + `dataset.theme`.
- [ ] `frontend/index.html` topbar right side adds `<button id="theme-toggle">` + sun/moon SVG icons.
- [ ] `frontend/js/app.js` adds a `setupThemeToggle()` function: on click toggle + write localStorage + trigger `Charts.retintAll()`.
- [ ] `frontend/js/charts/candle.js`:
  - Add a `readPalette()` helper that reads CSS variables.
  - Change `_baseOpts()` to use `readPalette()`.
  - Add a public `retint(ctx)` method.
- [ ] `frontend/js/charts/indicator_panels.js`:
  - Same `readPalette()` as above.
  - `_smallChart` uses `readPalette()`.
  - `retint(family, ctx)` method.
- [ ] `frontend/js/components/score_gauge.js`:
  - Move all hard-coded hex values into `readPalette()`.
  - The render function caches the last value so `retint` can re-render.
- [ ] `frontend/js/components/sparkline.js`:
  - Same as above.
- [ ] In `frontend/index.html` legend swatches' inline `style="background:#..."` become classes (`.swatch-blue`, `.swatch-orange`, `.swatch-green`, `.swatch-purple` each read the corresponding CSS var).
- [ ] Add transition: `html, body, .topbar, .score-card, .indicator-panel, .chart { transition: background-color 200ms ease, color 200ms ease }`.

**acceptance**:
- [ ] On theme toggle charts are not rebuilt (DevTools confirms zoom state is preserved).
- [ ] All elements read CSS variables; `grep '[a-fA-F0-9]{6}'` finds no hex literal (other than inside `:root`).
- [ ] WCAG AA: every text/bg pair ≥ 4.5:1 (verify via axe-core or Chrome DevTools).
- [ ] On first load in light mode the user sees no dark flash.
- [ ] localStorage `iosg-theme` stores the correct value.
- [ ] When OS `prefers-color-scheme` changes, it only responds if localStorage has no value.

### R8-3C · user item 4 (full English-isation)

**User verbatim** + Q11: include backend code comments + log.

**Implementation checklist**:

- [ ] `frontend/js/app.js:586-605` `COMPONENT_LABELS` 16 entries are translated to EN (see Part 3.3 table).
- [ ] Across all `frontend/**/*.{js,html,css}`, `grep '[一-鿿]'` → 0 hits.
- [ ] Across all `backend/**/*.py`, `grep '[一-鿿]'` → 0 hits (including docstrings, code comments, log messages).
- [ ] docs (README, PLAN, hand-off guide) are not touched.
- [ ] Commit messages — history is not rewritten.

**Note**: when translating Chinese backend comments, **preserve the original meaning in full**. For example:
- `# P0-F: HTML5 [hidden] 属性 MUST 胜过组件 display 规则` →
- `# P0-F: HTML5 [hidden] attribute MUST win over component display rules`

**acceptance**:
- [ ] `grep -rE '[一-鿿]' frontend/ backend/` reports 0 hits.
- [ ] `ma50_dev` vs `ma50_dev_z_40` are distinguishable in the UI (fixes the collision bug).
- [ ] API responses still have ASCII keys (already the case in Phase 1).

### R8-3D · user item 8 (tooltip enrichment)

**what**: see Part 3.3 for details.

**Implementation checklist**:

- [ ] New component `frontend/js/components/popover.js` (~80 lines):
  - `Popover.attach(element, getContent)` binds hover.
  - 200 ms open delay.
  - Moving the mouse inside the popover keeps it open.
  - Click outside dismisses.
  - Auto-adapts to theme via CSS variables.
- [ ] 12 panel headers `<header><span class="panel-title">...</span><span class="info-mark" data-tooltip="...">?</span></header>` use native `title`.
- [ ] The 16 Score-Breakdown component rows use `popover.attach` + a `COMPONENT_TOOLTIPS` map.
- [ ] 7 param-label info-marks use native `title`.
- [ ] Overall info-mark uses a popover with the full explainer.

**acceptance**:
- [ ] Every `.info-mark` + panel header has a real tooltip (`grep` finds no `title="?"` or `title=""`).
- [ ] All tooltips ≤ 280 chars: `Array.from(document.querySelectorAll('[title]')).forEach(e => console.assert(e.title.length <= 280))`.
- [ ] The popover appears 200 ms after hovering on a Score-Breakdown row.
- [ ] Hovering inside the popover does not dismiss it.
- [ ] The popover follows the theme switch and changes colour.

### R8-3E · R6/R7 carryover bugs (Q15 — fix all)

**R6-7 mobile-drawer actually working**:
- Debug `frontend/css/styles.css` `@media (max-width: 768px) .sidebar { position: fixed; ... transform: translateY(...) }`.
- Confirm R6-1 score-detail hoist has not broken the sidebar's DOM position.
- Playwright actual test: at 375×812 viewport the drawer is collapsed by default; tap to expand to `.expanded`; tap again to collapse.

**R7-3 gauge 0/100 label clipping**:
- `frontend/js/components/score_gauge.js` viewBox W goes from 220 to 240; add padding right/left = 6.
- Playwright screenshot `/tmp/r8c/19_gauge_closeup.png` — all three numbers readable.

**R7-4 indicator panel right price-axis chip overlap**:
- `frontend/js/charts/indicator_panels.js` `rightPriceScale.minimumWidth` from 56 to 72.
- Or, alternatively, move the OB/OS chip created by `createPriceLine` to the inner-side label mode of the y-axis.

**acceptance**:
- [ ] At 375×812 viewport screenshot, the drawer is collapsed by default and can be pulled up.
- [ ] All three gauge tick labels (0, 50, 100) are fully readable.
- [ ] The RSI panel 70/30 chip does not overlap the y-axis tick labels.

### Phase 2C acceptance: R8-γ audit round

Dispatch **2 fresh-context agents**:
- **Agent E**: Artist / Aesthetician — verifies the 21 light vars have a premium feel, tooltip enrichment, zero Chinese residue.
- **Agent F**: Senior Analyst — verifies Overall hero visual hierarchy, explainer content, mobile drawer working.

---

## Phase 2D — Tier B + Final Acceptance (Week 4)

### R8-4A · user item 2B (Tier B Ridge regression)

**what + how**: see Part 3.1 for details.

**Implementation checklist**:

- [ ] New script `scripts/train_tier_b.py`:
  ```python
  from sklearn.linear_model import RidgeCV
  import pandas as pd
  # 1. Read scores_history.csv → ~213k observations
  # 2. Join the corresponding OHLCV → forward 5d log return
  # 3. 16 atomic signal + 4 sleeve CS percentile features
  # 4. Date FE: per-date demean
  # 5. Walk-forward CV: 24m train / 1m test / monthly rolling
  # 6. RidgeCV(alphas=[0.1, 1, 10, 100])
  # 7. Coef stability across 12 folds; drop sleeves whose sign flips
  # 8. Write local_data/scoring/tier_b_weights.json
  #    {weights: {trend: 0.42, ...}, alpha: 1.0,
  #     cv_folds: [...12 folds of data...],
  #     holdout_spearman_rho_5d: 0.07,
  #     baseline_tier_a_rho_5d: 0.05,
  #     accept: true|false}
  ```
- [ ] Modify `backend/scoring/overall_score.py` to add `load_tier_b_weights()` + when requested with `?weights=regressed` use Tier B.
- [ ] `backend/api/routes_scores.py` adds support for the `weights` query parameter.
- [ ] Front-end score-card titles add `<select id="weights-toggle">` switching between `Theory | Data-driven`.
- [ ] Explainer modal Tier B row adds an actual coefficient table.

**acceptance**:
- [ ] `scripts/train_tier_b.py` runs to completion and outputs `tier_b_weights.json`.
- [ ] hold-out Spearman ρ ≥ Tier A baseline + 0.02 OR `accept: false` with the explainer explaining why.
- [ ] The front-end weights toggle switches between the two weight sets; the UI refreshes immediately (clicking the token re-computes).

### Phase 2D acceptance: R8-δ audit round

Dispatch **1 quant agent** to do the final cross-check:
- Tier A vs Tier B numerical sanity (same-token difference < 50 points).
- The full Phase-2 verdict synthesis (21+ commits with no regression).

---

# Part 5 — Detailed 4-Phase Timeline

| Week | Phase | Work units | Estimate | Audit |
|---|---|---|---|---|
| **Week 1** | **2A Infrastructure + Data** | R8-1A portability + integrity (Day 1)<br>R8-1B history → 2020 (Day 2-3)<br>R8-1C mcap/liquidity panel (Day 4)<br>R8-1D stocks integration (Day 5)<br>R8-α audit (end of Day 5) | 5 working days | 2 agents |
| **Week 2** | **2B Scoring + Analysis** | R8-2A Tier A overall + volatility indicator (Day 1-2)<br>R8-2B 9 canonical strategies + engine refactor (Day 3-4)<br>R8-2C score display + explainer (Day 5)<br>R8-β audit (end of Day 5) | 5 working days | 2 agents |
| **Week 3** | **2C UX Visual** | R8-3A overall hero polish (Day 1)<br>R8-3B light mode (Day 2)<br>R8-3C full English-isation (Day 3)<br>R8-3D tooltip enrichment (Day 4)<br>R8-3E R6/R7 carryover bugs (Day 5 morning)<br>R8-γ audit (Day 5 afternoon) | 5 working days | 2 agents |
| **Week 4** | **2D Tier B + Final** | R8-4A Tier B Ridge (Day 1-3)<br>UI weights toggle (Day 4)<br>R8-δ audit (Day 5) + buffer | 5 working days | 1 agent |

Total = 4 weeks = ~20 working days = ~25 commits.

---

# Part 6 — Master List of File Changes

## New files (22)

| File | Purpose | item |
|---|---|---|
| `backend/data/integrity.py` | boot integrity check | 10 |
| `backend/data/yfinance_client.py` | stocks data source | 7 |
| `backend/data/quarantine/` | dir for quarantining corrupt CSVs | 10 |
| `backend/indicators/volatility.py` | vol_20d/60d (for Risk sleeve) | 2 |
| `backend/scoring/overall_score.py` | Tier A + Tier B composite scoring | 2 |
| `backend/scoring/explainers.py` | Trend/Reversal/Overall explainer dicts | 1 |
| `backend/backtest/engine.py` | generic backtest engine | 6 |
| `backend/backtest/strategies.py` | 9 canonical strategies | 6 |
| `backend/backtest/universe_robustness.py` | universe-wide backtest | 6 |
| `backend/api/routes_market.py` | market_overview + data_coverage endpoints | 5, 11 |
| `backend/api/routes_robustness.py` | indicator-robustness endpoints | 6 |
| `backend/api/routes_scoring_meta.py` | explainer endpoint | 1 |
| `backend/api/routes_admin.py` | repair_token endpoint | 10 |
| `frontend/js/components/market_panel.js` | 5-tile market info | 5 |
| `frontend/js/components/popover.js` | local popover | 8 |
| `frontend/js/components/robustness_panel.js` | indicator-robustness UI | 6 |
| `scripts/train_tier_b.py` | Tier B training script | 2 |
| `scripts/run_history_extension.py` | one-shot history backfill | 11 |
| `scripts/pack_green_folder.sh` | green-folder zip packaging | 10 |
| `local_data/metadata/data_coverage.json` | per-token coverage | 11 |
| `local_data/metadata/stocks_universe.csv` | 40 US-stock config | 7 |
| `local_data/robustness_cache/` | backtest cache dir | 6 |

## Modified files (30 changes)

| File | Change | line range |
|---|---|---|
| `backend/main.py` | fix portability bug + boot integrity + stocks scheduler | 57, lifespan |
| `backend/config.py` | HISTORY_DAYS=2326 + stocks constants | 83 |
| `backend/data/coingecko_client.py` | extend `expected` field extraction | 276-290 |
| `backend/data/exchange_client.py` | 8 exchanges + Coinbase/Kraken/KuCoin/Bitstamp | 38-43, EXCHANGE_PRIORITY |
| `backend/data/fetcher.py` | `run_history_extension` + `run_stocks_daily_update` + `repair_token` | append |
| `backend/data/local_store.py` | schema-validation update | 39 |
| `backend/data/data_validator.py` | extend `TOP200_REQUIRED_COLUMNS` | 27-33 |
| `backend/services/data_service.py` | overall_score + rank_in_universe + asset_class | 99-152, 262-322 |
| `backend/scoring/trend_score.py` | unchanged (signals reuse) | — |
| `backend/scoring/reversal_score.py` | unchanged | — |
| `backend/scoring/ranking.py` | asset_class partitioning | 16-24 |
| `backend/backtest/golden_cross.py` | thin wrapper over `engine.run_backtest` | 32-139 |
| `backend/api/routes_tokens.py` | asset_class field + active flag | 14-94 |
| `backend/api/routes_scores.py` | overall + rank + asset_class filter + weights param | 16-115 |
| `backend/api/_validators.py` | regex allow A-Z + `.` | 26 |
| `frontend/index.html` | hero panel + market panel + tab strip + theme toggle + data coverage + robustness section | multiple |
| `frontend/css/styles.css` | light theme block + score-card-overall + market-panel + robustness-table + mobile-drawer fix | multiple |
| `frontend/js/app.js` | overall card + tabs + theme + i18n + popover wiring | multiple |
| `frontend/js/api.js` | getMarketOverview + getIndicatorRobustness + getScoringExplainer + getDataCoverage | multiple |
| `frontend/js/charts/candle.js` | readPalette + retint | multiple |
| `frontend/js/charts/indicator_panels.js` | readPalette + retint + minimumWidth fix | multiple |
| `frontend/js/components/score_gauge.js` | readPalette + xl size + viewBox fix | multiple |
| `frontend/js/components/sparkline.js` | readPalette | multiple |
| `requirements.txt` | add yfinance | append |
| `README.md` | green-folder + light mode + asset-class explanation | append |
| **All `backend/**/*.py`** | Chinese comments + log → English | multiple |

---

# Part 7 — Acceptance Method for the 4 Audit Rounds

Each audit round dispatches a fresh-context agent in the assigned role (does not read prior reports, does not look at each other, does not modify code).

## R8-α (end of Phase 2A) — 2 agents

**Agent A — System Architect**:
- Port 8091; writes report to `/tmp/AUDIT_R8a_arch.md`.
- Verifies the portability fix end-to-end (`DATA_DIR=/tmp/xxx`).
- Verifies the history extension really reaches back to 2020 (BTC/ETH first row ≤ 2020-01-01).
- Verifies the 8-exchange waterfall is actually used during daily-update.
- Verifies the quarantine + repair flow.

**Agent B — Data Scientist**:
- Port 8092; writes report to `/tmp/AUDIT_R8a_data.md`.
- Verifies `data_coverage.json` schema + `tier_breakdown` completeness.
- Verifies `stocks_universe.csv` has 40 rows + each ticker's OHLCV was successfully pulled.
- Verifies cross-sectional partitioning is really fully separated (crypto rank does not affect stocks rank).
- Verifies `market_overview` API values are reasonable.

## R8-β (end of Phase 2B) — 2 agents

**Agent C — Quant Researcher**:
- Port 8091; `/tmp/AUDIT_R8b_quant.md`.
- Verifies the Tier A `overall_score` formula (hand-computed vs API agree to 6 decimals).
- Verifies the walk-forward Spearman ρ test passes.
- Verifies the 9 robustness strategies' data are reasonable (not all marked unreliable).
- Verifies `indicator_robustness` cache invalidation is correct.

**Agent D — Product Designer**:
- Port 8092; `/tmp/AUDIT_R8b_design.md`.
- Verifies the Overall hero card visual hierarchy (above the fold, 240 px gauge, 56 px number).
- Verifies the 6 sleeves are mathematically consistent (weighted sum = overall_score).
- Verifies the explainer modal content is accurate + cites code literally.
- Verifies the rank chip is displayed correctly.

## R8-γ (end of Phase 2C) — 2 agents

**Agent E — Artist / Aesthetician**:
- Port 8091; `/tmp/AUDIT_R8c_artist.md`.
- Verifies all 21 light CSS variables pass WCAG AA.
- Verifies theme switch does not rebuild charts and preserves zoom.
- Verifies all 16 + 12 + 16 + 7 + 1 = 52 tooltips have real content.
- Verifies R6-7 drawer / R7-3 gauge / R7-4 chip — all three carryovers are really fixed.

**Agent F — Senior Analyst**:
- Port 8092; `/tmp/AUDIT_R8c_analyst.md`.
- Verifies `grep '[一-鿿]'` across the project returns 0 hits.
- Verifies popover 200 ms experience, no dismiss while hovering inside.
- Verifies the cumulative R8 fixes — no regression.

## R8-δ (end of Phase 2D) — 1 agent

**Agent G — Quant Final**:
- Port 8091; `/tmp/AUDIT_R8d_final.md`.
- Verifies Tier A vs Tier B numerical sanity (per-token difference range).
- Verifies the 24+ commits do not introduce regressions (mock-run the smoke test that passed at R7).
- Gives the final ship / needs-work verdict.

---

# Part 8 — Risk Register

| Risk | Trigger | Mitigation |
|---|---|---|
| OKX rate-limit 429 | History extension issues many requests in one shot | CCXT has built-in backoff; after 3 retries fall back to CG |
| Tier B Ridge ρ fails to beat Tier A | Insufficient historical sample or non-stationarity | Accept failure; UI hides Tier B toggle; keep Tier A as production |
| Stocks weekend data gaps | At cross-section ranking compute time | asset_class fully separated (Q6 decision); stocks only participate in ranking Mon–Fri |
| LightweightCharts theme-switch edge | Old version `applyOptions` lacks some fields | Fallback to destroy+recreate; warn user that zoom state is lost |
| 16 English labels inconsistent | Hard-coded in multiple places | Single source of truth in `COMPONENT_LABELS` |
| 4-phase span — failed rollback | Some intermediate phase introduces a regression | Per-phase audit + single revertable commit |
| yfinance suddenly degrades | Yahoo backend change, scrape fails | log warning + UI marks stocks as partially degraded; Phase 3 fallback to Polygon API |
| Real `.env` key accidentally committed | git add slips up | `.gitignore` already covers `.env`; `pack_green_folder.sh` automatically substitutes a placeholder |
| Phase 2D Tier B training takes too long | 24m × 12 fold = 288-month Ridge | Single training run < 5 min (pandas in-memory) |
| `data_coverage.json` schema change breaks UI | Future field additions | Front-end uses optional chaining; missing fields degrade gracefully |

---

# Part 9 — The First Thing To Do When Implementation Starts

Once ExitPlanMode is approved, do this in order:

### Step 0: copy the Plan file to the project root
```bash
cp "<source-plan-file>" "<project-root>/二期Plan-技术指标Dashboard.md"
cd <project root>
git add 二期Plan-技术指标Dashboard.md
git commit -m "docs: Phase 2 plan finalized"
```

### Step 1: R8-1A Day 1 first commit
Fix the `backend/main.py:57` portability bug:

```python
# Before
from backend.config import PROJECT_ROOT
...
store = LocalStore(Path(PROJECT_ROOT) / "local_data")

# After
from backend.config import DATA_DIR
...
store = LocalStore(DATA_DIR)
```

Commit: `fix R8-1A: backend/main.py honors DATA_DIR env var`.

### Step 2: keep going phase by phase — 4 phases × 5 days × ~5 commits/day.

---

# Part 10 — Phase 3 Candidates (not in Phase 2)

Recorded so we don't forget:
- HK stocks integration (5–15 .HK tickers).
- L2 orderbook liquidity depth (CG `/coins/{id}/tickers`).
- TheGraph DEX OHLC (Tier 2).
- Real Transformer composite (XGBoost + walk-forward).
- Complete Methodology stand-alone page (rich page, with every signal's formula + historical performance).
- Real-time (intra-day) data stream, supporting 5-min / 15-min candles.
- On-chain data expansion (whale alerts, on-chain indicators).
- Back-fill `scores_history` to 2020 (based on the extended OHLCV).

---

# Appendix A: User-Decision Quick-Lookup Table

| Q# | Question | Choice |
|---|---|---|
| Q1 | Composite-score tier | Do both A + B |
| Q2 | Tooltip style | Native + local popover |
| Q3 | Light-palette character | TradingView white, premium |
| Q4 | Overall-card layout | Strategy A full-width hero |
| Q5 | HK stocks | Skip |
| Q6 | crypto+stock ranking | Fully separated |
| Q7 | Overall breakdown content | 6 sleeves |
| Q8 | Implementation order | Architecture-first |
| Q9 | HK final | Skip; default CRCL |
| Q10 | pre-2023 data | CCXT exhaustive + CG fallback + 4-tier metadata |
| Q11 | English-isation scope | Include backend comments + log |
| Q12 | Acceptance approach | One audit round per module |
| Q13 | Tier 2/3 source | Skip |
| Q14 | Data-quality boundary UI | Data Coverage collapsible in scoring area |
| Q15 | R6/R7 carryover | Fix them all |
| Q16 | Tier B timing | Land together in Phase 2D |

# Appendix B: How This Plan Document Was Produced

- **Phase 1**: 3 Explore agents in parallel (scoring / frontend / data layer), ~10 min.
- **Phase 2**: 3 Plan agents in parallel (quant / architect / designer), ~15 min.
- **Phase 3**: 16 clarifying questions across 4 AskUserQuestion rounds; the user answered each.
- **Phase 4**: All findings + decisions integrated into this document.
- **Phase 5**: ExitPlanMode, waiting for user approval.

Total document size: ~32K characters (~1400 lines).
