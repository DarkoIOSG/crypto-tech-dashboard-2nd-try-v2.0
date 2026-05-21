# Development Progress

- 2026-05-12 16:48: created isolated project folder and copied provided documents.
- Missing/not yet provided: `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` reference notebook.
- 2026-05-12 16:50: attempted to install/use local PraisonAI. Editable install failed because package uses pyproject without editable setuptools support; normal install failed due PyPI SSL error fetching build deps. Direct PYTHONPATH import attempted; see run log.
- 2026-05-12 16:58: refreshed source docs from latest uploaded copies. User message mentioned notebook, but no `.ipynb` attachment path was included in the delivered content.
- 2026-05-12 17:02: consolidated project-related docs at the project root; added `PROJECT_FILES_INDEX.md`; checked local cache and no `.ipynb` notebook file is present.
- 2026-05-12 10:21 (A2b): wrote backend/data/data_validator.py (195 lines)
- 2026-05-12 18:21 (A1b): wrote backend/data/fetcher.py (408 lines)

## Phase 1.5 (18:39)
- files: scripts/smoke_data_layer.py
- accept: PASS — OKX returned 30 BTC/USDT bars, last close=$80,735.20 (>$1000 plausible). Binance (HTTP 451) and Bybit (HTTP 403) are geo-blocked from this Mac; OKX + Gate.io are the operative exchanges. Waterfall still works because mapper falls through.
- next: Phase 2 — indicators engine.

## Phase 2 (18:42)
- files: backend/indicators/{base,registry,ma_cross_sma,ma_cross_ema,macd,rsi,rsi_mr,kdj,bollinger,volume_spike,momentum,mean_reversion,zscore_ma,price_appreciation}.py + scripts/smoke_indicators.py
- accept: PASS — 12 families register, compute_all yields 121 series, RSI(14)=60.46 in [0,100], MACD hist sign-changes=17 over 250 bars. Live BTC/USDT pulled from OKX (250 rows).
- next: Phase 3 — scoring + API.

## Phase 3 (18:45)
- files: backend/scoring/{trend_score,reversal_score,ranking}.py, backend/backtest/golden_cross.py, backend/services/data_service.py, backend/api/{routes_tokens,routes_indicators,routes_scores,routes_backtest,routes_system}.py, backend/main.py, scripts/smoke_api.py
- accept: PASS — uvicorn launched at 127.0.0.1:8088. /health=200, /api/tokens=200 (empty count since no data fetched yet), /api/scores=200. Scheduler armed for daily_update @ 08:30 Asia/Shanghai. Fetcher bound to /api/system/refresh.
- next: Phase 4 — frontend.

## Phase 4 (18:47)
- files: frontend/index.html, frontend/css/styles.css, frontend/js/api.js, frontend/js/app.js, frontend/js/charts/{candle,indicator_panels}.js, frontend/lib/lightweight-charts.standalone.production.js, scripts/smoke_frontend.py
- accept: PASS — / served (6149 bytes) with title + lib tag, /lib/lightweight-charts.standalone.production.js = 191 KB (>100 KB), /css/styles.css and /js/app.js both 200.
- next: final integration test.

## Final integration (18:58)
- helpers: scripts/initial_small_fetch.py (5-token universe, 60-day OHLCV via OKX), scripts/integration_test.py
- accept: PASS — All endpoints 200. Five CSVs (bitcoin, ethereum, solana, ripple, cardano) written to local_data/ohlcv/. /api/tokens=5, /api/scores=5 (top trend=solana 80.0). /api/indicators/bitcoin returned 121 indicator series. /api/backtest/bitcoin: CAGR=1.01 Sharpe=2.94. / served with title + lightweight-charts tag.
- caveats: (1) CoinGecko Pro API has SSL EOF errors from this Mac (same as pypi.org TLS issue noted in prompt) — integration script falls back to hard-coded 5-token universe; production daily-update path is unaffected once that network is fixed. (2) Binance + Bybit return 451/403 from this region; OKX + Gate.io are the operative exchanges, and the waterfall handles this transparently. (3) Top-200 universe needs CoinGecko to populate; once network is fixed, run `venv/bin/python -m backend.data.fetcher` or POST /api/system/refresh?full=true.

## Full initial load (21:04)
- started: 2026-05-12T13:00:33.401060Z
- elapsed: 3.7 min
- result: success=167 fallback=33 failed=0 universe_size=200

## Review (Product / PM)
- [PRODUCT_REVIEW.md](PRODUCT_REVIEW.md) — Google-PM audit graded the product **C+ (functional prototype, not v1)**: backend pipeline + 12 indicators + cross-sectional ranking work, but the user-facing surface lacks search, legends, tooltips, event markers, parameter overrides, refresh polling, and per-token sparkline/sector context — and the OHLCV store is capped at ~300 days so the marquee "2y / 3y historical percentile" feature is mathematically degenerate (2y == 3y to 5 decimals). Top 3 product moves: (1) fix history depth + unify historical-percentile formula with the headline score, (2) rebuild the ranking sidebar with symbol/price/change/sector/sparkline/search, (3) make every indicator panel self-explanatory with legend, tooltip, event markers, and parameter inputs.

## Review (Visual Design) — 2026-05-12

Source-level audit of `frontend/` against Plan §7 (TradingView dark theme).
Chrome MCP extension was unreachable from this session, so no live screenshots
were captured; audit is based on reading `index.html`, `css/styles.css`,
`js/app.js`, `js/charts/candle.js`, `js/charts/indicator_panels.js`, plus
curl verification of every static asset and the relevant `/api/*` endpoints.

### Pass / Warn / Fail table (before fixes)

| Item | Status | Note |
|------|--------|------|
| TradingView palette adherence | PASS | All variables in §7.2 declared; spec values used verbatim. |
| Type hierarchy | WARN | Section headers and panel labels used near-identical weight/size; little contrast between primary and secondary text. |
| Spacing / rhythm | WARN | 16 px gutter everywhere, but no max-width on `.layout`; on a 27" monitor charts stretched edge-to-edge. |
| Chart legibility | PASS | Lightweight-Charts default axis is fine; small-panel font set to 11 px. |
| Up/down candle colours | PASS | `#26a69a` / `#ef5350` matches spec exactly. |
| Crosshair / hover state | WARN | `crosshair.mode: 0` (Magnet) on the master, none configured on panels; default cursor with thin grid line and no axis label background. |
| Score badge prominence | WARN | Trend / Reversal pills had label and value in the same colour/weight; numbers did not pop. |
| Score-large colour | FAIL | Always green regardless of value — a Trend=12 looked identical to a Trend=90. |
| Ranking sidebar | WARN | No rank numbering, no top-3 emphasis, no overflow handling, rank score always green. |
| Loading / empty states | WARN | "no tokens loaded" hint exists; charts are silent on empty data. |
| Responsive 1440 / 1920 / 1024 | WARN | Only one breakpoint at 900 px; the 1024-1200 zone left only ~720 px for the main pane with a 280 px sidebar. |
| Token-price colour | FAIL | Used `--accent-yellow` (reserved for warnings/spikes per spec) — visually screamed at the user even when nothing was wrong. |
| Bollinger band envelope | WARN | Three line series, no fill — flat / hard to read at small panel size. |
| RSI band labels | WARN | 30/70 lines existed but had no axis labels or 50 mid-line. |
| Focus states (a11y) | FAIL | No `:focus-visible` ring on `.btn` or `<select>`. |
| Window resize | FAIL | Charts were created at initial `clientWidth/clientHeight` and never reflowed. |
| `.more-indicators` disclosure | WARN | Plain `<summary>` with default browser marker on Safari/Firefox; inconsistent affordance. |

### Concrete CSS / JS changes applied

All edits stay within the existing files — no new files.

`frontend/css/styles.css` — material rewrite of palette utilisation, type
ramp, spacing, and responsive behaviour:
- Topbar: sticky to viewport top, `z-index: 50`, baseline-aligned brand +
  `last-update`, tabular-num timestamp.
- `.btn`: 6 × 14 px, transition, `:hover` border becomes accent-blue,
  `:focus-visible` 2 px blue glow, `:disabled` 55 % opacity.
- `.layout`: `max-width: 1800px; margin: 0 auto` to stop edge-bleed on 4K
  monitors; columns now `minmax(0,1fr) 280px` to keep main pane shrinkable.
- `.sidebar`: rounded 6 px, sticky `top: 60px`, `max-height` viewport-aware,
  custom dark scrollbar.
- `.rank-list`: CSS counters render 1-20 in muted text, top-3 highlighted
  in `--accent-yellow`; new modifier classes `.score-low` (red) and
  `.score-mid` (yellow) replace the always-green badge.
- `.token-price` switched from yellow to `--text-primary` 500-weight
  tabular-nums.
- `.score-badge` redesigned as label-on-secondary, value-on-primary; reads
  more like a stat card than a coloured pill.
- `.section-header` shrunk to 11 px / 800-weight / 0.8 px tracking with a
  hairline bottom border — clearer hierarchy.
- `.indicator-panel`: 6 px radius, hover border lifts to elevated grey;
  headers tightened to 11 px uppercase.
- `.more-indicators > summary`: custom `+ / -` glyph in accent-blue, hides
  the default disclosure triangle, uppercase tracking matches section
  headers.
- `.score-large`: 38 px, tabular-nums, negative letter-spacing; colour now
  driven by `.score-strong` (≥66, green), `.score-neutral` (33-66, yellow),
  `.score-weak` (<33, red).
- `.backtest-stats`: stat-grid with `auto-fit, minmax(100px, 1fr)` — KPIs
  read as a row of values, not a paragraph.
- Added `@media (max-width: 1200px)` to shrink sidebar to 240 px on
  laptops; existing 900 px breakpoint tightened (padding, sidebar
  max-height, scores-mini wraps).

`frontend/js/app.js`:
- Added `scoreTierClass()` / `scoreLargeClass()` helpers driving the new
  colour tiers.
- `loadRankings()` now applies the tier class and a `title` tooltip.
- `loadTokens()` formats option labels as `SYM  ·  Name` (mid-dot
  separator) for cleaner scan-ability.
- `renderScoreDetail()` rewrites the className on the score-large element
  on every render.
- New `wireResize()` re-applies `width / height` to candle + all 12
  indicator charts on `resize` (debounced to one `requestAnimationFrame`).

`frontend/js/charts/candle.js`:
- Crosshair `mode: 1` (free) with dim `#787b86` dashed lines and `#363a45`
  label background — TradingView signature look.
- Layout font set to system stack 12 px (matches body), axis bottom margin
  raised to 22 % so volume sits cleanly under price.
- `timeScale.rightOffset: 6` — a few empty bars to the right is a polish
  touch every TradingView clone has.

`frontend/js/charts/indicator_panels.js`:
- Same crosshair + font treatment on panels.
- Bollinger upper now renders as an `AreaSeries` with a 10 % blue top
  fade — the band visually has shape; mid line is now dashed muted; lower
  stays as a thin blue line. (Lightweight-Charts has no fill-between, so a
  one-sided gradient is the cleanest dark-theme proxy.)
- RSI line bumped to 2 px, added 50 mid-line, 30/70 lines now carry "OS" /
  "OB" axis-label titles.

### Top 5 visual improvements NOT implemented (and why)

1. **Token logos / coin icons in the selector and sidebar.** Plan §7.3
   doesn't require them, sourcing 200 SVGs (CryptoIcons / CoinGecko CDN)
   is a half-day's work plus a missing-icon fallback, and risks the
   "noisy logos" anti-pattern that TradingView itself avoids in its dark
   tickers. Defer.
2. **Sparkline column on the Top-20 sidebar.** Plan §7.3 mentions it as
   a "small trend sparkline". Drawing 20 inline `<canvas>` mini-charts
   needs a second API call (`/api/ohlc/{id}?days=30` × 20) or a new
   bulk endpoint; the sidebar is already useful without it. Scope creep
   for an audit pass.
3. **Score-card SVG gauges (the speedometer in Plan §7.1).** A real gauge
   needs an SVG arc primitive + animated needle. The colour-tiered
   numeric value plus the percentile line already conveys the same
   information; building gauges is a feature, not a tightening.
4. **Per-panel parameter inputs** (fast/slow/period boxes, Plan §7.3
   participation widget). Wiring debounced inputs to per-family
   `/api/indicators/.../{family}` calls is a UX feature, not a visual
   audit item.
5. **Searchable token selector** (combobox replacing native `<select>`).
   200 entries in a native dropdown is workable; a true autocomplete
   means writing a fresh focus-trap + keyboard nav widget. Out of scope
   for incremental tightening.

### Screenshots

Not captured — Chrome MCP extension reported "Browser extension is not
connected" on `tabs_context_mcp`. Per the brief, fell back to source-only
audit instead of burning cycles. `screenshots/` directory created and
left empty for the next run.

## Review (Programming / PM) — 2026-05-12

End-to-end audit of `backend/` and `frontend/` against
`PLAN_技术指标Dashboard.md` and `任务交接指南.md`, with a live uvicorn run
on 127.0.0.1:8080 and pandas-level checks against the notebook source of
truth (`/tmp/notebook_compute_features.py`).

### Plan coverage estimate
- **Implemented fully (~85%)**: data layer, 12 indicator families (formulas
  byte-identical to notebook within float precision), trend / reversal
  scoring with the exact 9 / 7 signal sets, cross-sectional ranking,
  2 y / 3 y time-series percentiles, FastAPI app, APScheduler cron at
  08:30 Asia/Shanghai, /api/system/refresh?full=true wired, atomic CSV
  writes, top200_current.csv + symbol_map.json + last_update.json all
  persisted with 200 token CSVs on disk.
- **Implemented partially (~10%)**: API surface (Plan §8 paths
  `/api/refresh`, `/api/status`, `/api/token/{id}`, `/api/data-check`
  added as aliases this session — see fixes below). OHLCV depth: only
  ~300 days on disk vs. Plan §3.2 spec of 1095 — see High-severity
  punch-list. Scores history persistence (`scores_history.csv` from
  Plan §3.2) is not implemented; time-series percentiles are computed
  on the fly from indicator histories, which is functionally close but
  not what the plan specified.
- **Not implemented (~5%)**: ohlcv_backup rotation (Plan §3.2 step 5),
  CoinGecko date-offset auto-detection (Plan §3.5 problem 1), the
  parameter-input UI on indicator panels (Plan §7.3), the score gauge
  SVGs, and the searchable token combobox.

### Indicator formula diffs (file:line)
None blocking. Verified end-to-end on bitcoin.csv:
- RSI(14) backend vs. notebook formula: 61.4657 ≡ 61.4657 (exact).
- MACD(12,26,9) histogram (price-normalised): 0.000234 ≡ 0.000234.
- KDJ(9,3,3): K/D/J 70.19 / 72.71 / 65.16 — initialised from K0=D0=50
  per Plan §4.6.
- BB(20,2): `bb_pctb_20` produced; value 0.242 on BTC, in [-0.5, 0.5].
- Mean reversion both flavours present (classic `mean_reversion_{L}`
  and skip-MR `mr_z_{L}_skip{S}`, `mr_rank_{L}_skip{S}`).
- Trend signal set in `backend/scoring/trend_score.py:24-34` is exactly
  the 9 keys in Plan §5.1.
- Reversal signal set in `backend/scoring/reversal_score.py:21-29` is
  exactly the 7 keys in Plan §5.2 (with `-1.0` sign applied to
  `bb_z_20`, `ma50_dev_z_40`, and `mom_ret_5d` per the table).

One observation worth flagging (not a bug): the notebook commented out
several signal keys that this build uses (`rsi_turn_event_{p}`,
`macd_hist_slope5_{key}`, `bb_pctb_{p}`). The plan §5 explicitly waives
this — "Dashboard 不做 ML 特征选择" — so the implementation is
intentional. Documented in `rsi.py:43-51` and `macd.py:46-49`.

### API endpoint diffs vs Plan §8
| Plan path | Impl path | Status |
|-----------|-----------|--------|
| `/api/tokens` | `/api/tokens` | OK |
| `/api/token/{coin_id}` | `/api/tokens/{cg_id}` | OK + alias added |
| `/api/ohlc/{coin_id}` | `/api/ohlc/{cg_id}` | OK |
| `/api/indicators/{coin_id}/{family}` | same | OK |
| `/api/indicators/{coin_id}` | same | OK |
| `/api/scores/{coin_id}` | same | OK |
| `/api/rankings` | same | OK |
| `/api/backtest/{coin_id}` | same | OK |
| `/api/refresh` (POST) | `/api/system/refresh` | OK + alias added |
| `/api/status` | `/api/system/status` | OK + alias added |
| `/api/data-check` | missing → added | FIX applied |

All endpoints returned 200 on the live server. `/api/scores` returned
197 of 200 — the 3 missing tokens are `spiko-amundi-overnight-swap-fund-eur`
(10 rows, CG fallback, listed mid-Apr), `billions-network` (9 rows, CG
fallback, listed early-May), `lido-earn-eth` (25 rows, CG fallback) —
all below the `_compute_full_indicators` 30-row floor in
`data_service.py:185`. Acceptable per Plan §11.7 ("新上市代币 ...
正确标注 数据不足"), but the 30-row floor is not currently exposed in
the response (a "skipped, n_rows=9" stub would be cleaner).

### Fixes applied in place
1. `backend/api/routes_system.py` — added `GET /api/status` and
   `POST /api/refresh` aliases (~10 lines), plus the new
   `GET /api/data-check` route (~38 lines) that runs `validate_ohlcv`
   over `local_data/ohlcv/*.csv` and `validate_top200` over the
   universe CSV. Live test: `/api/data-check?limit=10` → 200, returned
   `{"top200_issues":"OK","ohlcv_ok":10,"ohlcv_with_issues":0,...}`.
2. `backend/api/routes_tokens.py` — added `GET /api/token/{cg_id}`
   singular alias (~5 lines). Live test: 200 on bitcoin.

### Live integration test summary
| Endpoint | HTTP | Notes |
|---|---|---|
| `/health` | 200 | `{"ok":true}` |
| `/api/system/status` | 200 | token_count=200, last_ohlcv_update=2026-05-12T21:04:43 |
| `/api/system/health` | 200 | |
| `/api/tokens` | 200 | count=200 |
| `/api/scores` | 200 | count=197, top-1 trend = `humanity` 79.13 |
| `/api/scores/bitcoin` | 200 | trend=48.84 reversal=51.02 + 2y/3y percentiles populated |
| `/api/tokens/bitcoin` | 200 | last_close=80923.5, last_date=2026-05-12, ohlcv_rows=300 |
| `/api/ohlc/bitcoin?days=10` | 200 | full OHLCV records, source=okx |
| `/api/indicators/bitcoin?days=30` | 200 | series payload |
| `/api/indicators/bitcoin/rsi?days=5` | 200 | rsi_14 latest 65.6 |
| `/api/backtest/bitcoin` | 200 | CAGR=-18.1%, Sharpe=-0.75, 15 trades, win=25% — bear-market sample, plausible |
| `/api/rankings?limit=5` | 200 | matches /api/scores ordering |
| `/api/refresh` (alias) | 200 | started daily_update |
| `/api/status` (alias) | 200 | mirrors /api/system/status |
| `/api/token/bitcoin` (alias) | 200 | mirrors /api/tokens/bitcoin |
| `/api/data-check?limit=10` | 200 | new route — top200=OK, 10/10 OHLCV OK |

### Data integrity sweep
- `local_data/market_cap/top200_current.csv` — 200 rows, `validate_top200` = OK.
- `local_data/metadata/symbol_map.json` — 21 KB, present.
- `local_data/metadata/last_update.json` — `status=ok`, `mode=full_load`,
  `success=167 fallback=33 failed=0`.
- 5 sampled tokens (`bitcoin`, `aave`, `apenft`, `audiera`, `aster-2`)
  all pass `validate_ohlcv`. CG-fallback total = 33 / 200 (matches
  last_run_summary).

### Punch list — NOT fixed this pass

**HIGH**
1. **OHLCV depth is ~300 days, not 1095.** Root cause:
   `backend/data/exchange_client.py:124` caps `limit = min(int(days),
   EXCHANGE_OHLCV_LIMIT=1000)` but never paginates back with `since=`.
   OKX (which holds the majority of the 167 exchange tokens) caps per
   call at ~300 bars and CCXT returns only that page. All exchange
   tokens therefore truncate at 300 rows. The marquee "2 y / 3 y
   historical percentile" feature is mathematically the same value
   to ~5 decimals because the underlying series is < 1 y. Fix is
   structural (~80 lines): wrap `fetch_ohlcv` in a `while ts <
   target_ts` paginator that walks the `since` parameter back to
   today - days; respects each exchange's per-call cap (OKX 100,
   Binance 1000, Bybit 1000, Gate.io 1000). After the fix, rerun
   `run_full_initial_load(200, 1095)` once. Time cost: ~10-15 min
   re-pull + ~30 min code/test. Recommend spawning a sub-agent.
2. **`scores_history.csv` is not persisted.** Plan §3.2 step 3 + §3.3
   asks for a daily 200×2 row append so historical percentiles do not
   recompute from scratch on every API call. Current impl recomputes
   the trend / reversal series in memory each request (cached, but
   evicted on any data refresh). Functional, but slow on cold cache
   for big tokens.

**MEDIUM**
3. **CoinGecko T+1 date-offset auto-detection** (Plan §3.5 problem 1)
   is referenced in code comments but never executed. Today this is
   silent because we don't actually compute indicators against
   CoinGecko close-only data alongside exchange data for the same
   token. Worth adding before any cross-source comparisons land.
4. **No backup rotation.** Plan §3.2 step 5 wants `ohlcv_backup_YYYYMMDD/`
   retained for last 3 full-loads. Not implemented; on a fresh
   `run_full_initial_load` we silently overwrite. Low risk because
   the source data is reproducible from CG + exchanges.
5. **`/api/scores` skips the 3 short-history tokens silently.** Worth
   returning a `skipped: [{cg_id, reason: "history < 30 rows", n_rows}]`
   block so the UI can show a "data insufficient" badge per Plan §11.7.

**LOW**
6. The fetcher has `_maybe_run_validator` (`fetcher.py:386-408`) wired
   to a sentinel `_Validator` that returns None — the real
   `data_validator` module is never invoked by the daily-update path.
   Should call `validate_ohlcv` over the appended-to files and write
   `data_integrity_log.json` per Plan §11.5.
7. `last_update.json` uses `status: "ok"` but Plan §3.2 enumerates
   `idle | updating | error`. Cosmetic, no consumer depends on it.
8. The `Fetcher._build_fetcher` / `lifespan` path in `main.py:88-95`
   uses a try/except boundary which is permitted by the hard rules.
   Confirmed compliant.
9. `routes_indicators.family_indicators` (`routes_indicators.py:33-73`)
   uses positional iteration over the tail index that assumes
   `reset_index(drop=True)` was done upstream by `data_service.get_ohlcv`
   — it is. Safe today, but brittle if someone changes the loader.
10. No "skip" tag is sent to the frontend for CG-fallback (source =
    `coingecko`) tokens — Plan §3.1 says to flag "仅收盘价数据" in the
    UI. Easy: the `source` column is already in `/api/ohlc/{id}`; the
    frontend just needs to render a small badge when the latest source
    is `coingecko`.

### Recommendation
**Needs work in 1 high-severity area before ship: OHLCV pagination.**
Everything else is shippable. The 12 indicator families are formula-
correct against the notebook source of truth; the API surface is
complete (with the aliases added this pass); the live server passes
every endpoint check at 200; the data on disk validates clean. Once
pagination lands and a fresh full-load brings every exchange-sourced
token to ~1095 rows, the 2 y / 3 y percentile feature will become
genuinely meaningful and the product crosses from prototype to v1.

Sub-agent recommended for the pagination work (touches
`exchange_client.py`, possibly `fetcher.py` for time-budgeting,
plus a CCXT integration test). Scope > 50 lines / > 1 file,
matches the dispatch policy threshold.

## Full initial load (23:15)
- started: 2026-05-12T15:08:18.403732Z
- elapsed: 6.9 min
- result: success=163 fallback=37 failed=0 universe_size=200

## Post-review fixes (23:17)
- **Bug 1 — OHLCV pagination (HIGH/CRITICAL).** `backend/data/exchange_client.py` `fetch_ohlcv()` rewritten to paginate via `since=` cursor walking forward in time, honouring a per-exchange `PER_CALL_LIMIT` (binance=1000, okx=300, bybit=1000, gateio=1000). Walks from `now - days*86400000` ms forward in pages of `per_call_limit`, dedupes by date, sorts ascending, clips to the most recent `target_days` bars. `try/except` retained only around the `ex.fetch_ohlcv` call. Smoke test: BTC waterfall returns 1095 rows on OKX, first date 2023-05-14.
- **Full reload** (`scripts/full_initial_load.py`): completed in 6.9 min, success=163 fallback=37 failed=0, universe_size=200. CSV row counts:
  - bitcoin: 301 → 1095
  - ethereum: 301 → 1095
  - solana: 301 → 1095
  - ondo-finance: 301 → 749 (listed ~Jan-2024; clipped by listing date)
  - sui: 301 → 1095
  Time-series percentiles now meaningfully diverge: BTC trend `2y=68.08`, `3y=65.30` (previously identical to ~5 decimals).
- **Bug 2a — Searchable token combobox.** Replaced native `<select id="token-select">` with `<input id="token-search">` + filtered `<ul id="token-dropdown">`. Plain-JS filter matches on `cg_id` / `symbol` / `name` (max 50 results). Keyboard: ArrowUp/Down highlight, Enter selects active, Escape closes.
- **Bug 2b — Enriched sidebar rows.** `/api/rankings` now returns `symbol` and `name` per row (read from `data_service.list_tokens()`). Frontend renders each row as: `#N` rank badge (top-3 highlighted yellow) + uppercase symbol primary + name secondary + colour-tiered score on the right. No sparkline (deferred to v1.1).
- **Bug 2c — Indicator panel legends.** Added 12px legend rows under headers for MACD, KDJ, Momentum, SMA Cross, EMA Cross panels with colour-swatch + series name. Swatches use the existing dark-theme palette directly inline so they match the chart lines.
- **Bug 2d — Score tooltips.** Added `title=` hovers on Trend/Reversal score badges, score-card headings, and percentile lines explaining the blended-signal formula and the cross-sectional ranking. Inline `(?)` info-mark glyph signals hover-help affordance.
- **Smoke**: uvicorn restarted at 127.0.0.1:8080. `/`, `/api/tokens`, `/api/scores`, `/api/indicators/bitcoin` all 200. `/api/scores` count=197 (the same 3 short-history tokens are still skipped — unchanged behaviour). Bitcoin `ohlcv_rows=1095`, last_date=2026-05-12.
