# Product Review — IOSG Crypto Tech Dashboard

Reviewer: Google PM (hands-on audit), 2026-05-12
Build under review: 200 tokens loaded, OHLCV last_date 2026-05-12, full-load run at 21:04:43 (`status=ok`, `success=167`, `fallback=33`).

---

## TL;DR

**Grade: C+ (functional prototype, not a v1 product).** The skeleton is there — backend pipeline runs, 12 indicator families compute, scores rank cross-sectionally, and the frontend draws every chart the Plan named. But the surface that the user actually touches is missing almost every affordance that turns a chart wall into a decision tool: no search, no token symbols in rankings, no legends, no tooltips, no parameter overrides, no indicator markers (golden-cross arrows, volume-spike bars, KDJ cross), and — most damaging — only ~300 days of OHLCV is stored on disk, so the headline "2y / 3y historical percentile" feature is mathematically degenerate (the 2y and 3y windows clip to the same ~10-month series and the displayed value uses a *different* metric than the headline trend_score). A sophisticated trader would distrust this dashboard within 60 seconds of opening it.

---

## Job-to-be-done

**Primary user:** A crypto-native fundamental/quant analyst (likely an IOSG investor or research staffer) who already has a 200-coin watchlist and wants a daily "technical pulse" to triage which names deserve a deeper look.

**Decision the product supports:** *"Of the Top-200 by market cap, which 10-20 names are technically setting up for a continuation (trend) or a mean-reversion bounce (reversal), and how does today's reading rank within that token's own recent history?"*

**Success state:** Open the page, see today's top-of-list reversal/trend candidates in <3 seconds, click into one, glance at 6 indicator panels + score breakdown, decide whether to add the name to a fundamental research queue. **The product does not pretend to be a trading terminal — it is a screener.**

---

## What works

- Backend pipeline actually runs end-to-end: 200 tokens fetched, 167 via exchanges + 33 via CoinGecko fallback, indicators + scores compute, APIs respond <1s.
- Cross-sectional ranking is sensible: top trend names (`humanity`, `akash-network`, `venice-token`) have momentum at the 98-100 percentile — the model isn't broken.
- Multi-exchange waterfall is working (`source` column in CSVs shows `okx` for BTC, etc.) — credit to the data layer.
- Charts render with TradingView Lightweight Charts and the dark theme matches the Plan's spec values exactly.
- The main candle chart drives time-axis sync to all 12 indicator panels via `subscribeVisibleLogicalRangeChange` (Plan §7.3 explicit requirement — implemented).

---

## What's broken or missing (prioritized punch list)

### P0 — blocks the core job

1. **Historical depth is ~300 days, not 1095 (Plan §3.2 promised 3 years).** Every OHLCV CSV is exactly 300-301 rows (sample: `bitcoin.csv` 301 lines, `ethereum.csv` 301 lines, earliest row `2025-07-17`). The `last_run_summary.history_days` field claims `1095` but reality contradicts it — likely the fetcher hit a cap (CCXT default `limit=300`?) silently. Consequence: every downstream feature that depends on multi-year history is degraded.
2. **The "2y / 3y historical percentile" is degenerate and misleading.** BTC currently shows `trend_ts_2y_percentile = 79.33`, `trend_ts_3y_percentile = 79.33` — *identical to 5 decimals* because both windows clip to the same ~300-day series. The user thinks they're reading two independent percentiles; they're reading the same number twice. Plus, `data_service._token_trend_score_history` averages raw signed signals while the headline `trend_score` is the cross-sectional percentile rank of that sum — two different distributions on the same axis. A user comparing "today: 49" with "2y rank: 79th" will conclude the score is on a different scale than it is.
3. **Ranking sidebar is unusable for discovery.** It shows `cg_id` strings (`venice-token`, `injective-protocol`) with no symbol, no price, no 24h change, no sparkline (Plan §7.3 explicitly required a sparkline), no sector tag, and no way to filter by sector or mcap band. A user staring at `humanity / 79.1` has zero context to act on.
4. **Token selector is a raw `<select>` with no search.** 200 options in a native dropdown — finding `ondo-finance` requires scrolling 60+ items. Plan §7.3 explicitly said "可搜索的下拉菜单, 支持按 symbol 和 name 模糊搜索." Not implemented.
5. **No legend on any indicator panel.** RSI has a single purple line with 30/70 horizontal lines — fine. But MACD has three series (blue, orange, green/red histogram) and no labels; KDJ has three lines (K/D/J) all colored differently with no key; Momentum draws 4 colored lines representing 5d/10d/20d/30d with no legend; Bollinger draws upper/mid/lower with no axis labels. A new user cannot read these charts without reading the source code.

### P1 — significant degradation

6. **Volume-Spike panel does not show volume.** Plan §4.8 and §7.3 specified "volume bars with yellow highlight on spike days." Implementation: a single yellow `vol_ratio_14` line with a `3.0` price line. The actual volume bars are on the main candle chart but with no spike highlighting either. The most visually distinctive indicator in the Plan is now a barely-readable ratio line.
7. **No cross/event markers on any chart.** SMA/EMA panels have no golden/death-cross triangles (Plan §4.1 step 9-10, §4.2). MACD panel has no zero-cross dots. KDJ panel has no K/D cross markers. The indicators compute `sma_cross_up`, `sma_cross_down`, `macd_cross_event`, `kdj_golden_cross` — frontend simply ignores them.
8. **No parameter overrides anywhere.** Plan §7.3 was specific: "每个指标面板右上角有参数输入框 ... 修改后 300ms 防抖 ... 重置按钮." Backend supports `?fast=5&slow=20` overrides in `/api/indicators/{cg_id}/{family}`. Frontend never calls that variant. Users cannot try MACD(5,10,4) or RSI(21) — a major value prop of a technical dashboard.
9. **Refresh button is "fire and pray" — no real status feedback.** `onRefreshClick` calls `POST /api/system/refresh`, sets a 5-second `setTimeout`, then unconditionally resets the button. If the refresh takes 30s or fails, the user sees stale data with a green "Refresh" button. Plan §7.3 specified polling `/api/status` until completion.
10. **"Last update" timestamp is opaque.** Header reads `last update: 2026-05-12T21:04:43` — no timezone, no relative time ("3 minutes ago"), no freshness color signal (green/yellow/red). The `mode: "full_load"` and `success/fallback` counts are buried in `/api/system/status` and never surfaced.
11. **Score breakdown lists 9/7 cryptic component keys with no explanation.** `mom_ret_10d`, `macd_hist_slope5_12_26_9`, `kdj_os_distance` — raw indicator names with raw float values (`-2.2578`). No tooltip, no plain-English description ("J line vs oversold band"), no scale hint ("range ≈ ±2"). The user cannot tell if `-1.04` for `rsi_dist_os_14` is good, bad, or normal.
12. **No "what is this score" explanation in the UI.** Trend = 48.8, Reversal = 51.0 — what are these? 0-100 percentile or absolute? Is higher better? The Plan describes a 9-signal trend + 7-signal reversal blend but the user has no hover, no `?` icon, no docs link. A score without an explanation is opaque.
13. **`/api/backtest` returns CAGR -18% on BTC SMA(5/20)** — that's a legitimate result, but the UI provides no equity curve plot (the `equity_curve` array is returned and discarded), no benchmark (HODL CAGR for the same window), and no trade markers on the main chart. The backtest is API-complete but UI-orphaned.
14. **No data-quality signal on tokens with fallback source.** 33 tokens (16.5%) are CoinGecko-fallback with no real high/low/volume. Plan §3.1.2 specified "前端标注 `仅收盘价数据`" — the `/api/tokens` response doesn't even expose the source, the dropdown shows them mixed with full-OHLC tokens, and KDJ silently renders empty for them.
15. **Search/sort/filter on the rankings list is absent.** Only the Top 20 is fetched. No "show top 50", no sector filter, no mcap band, no "exclude fallback tokens" toggle. For a screener product, this is the headline workflow.

### P2 — polish

16. **Token detail card has no 24h change.** The Plan asked for "当前价格和 24h 涨跌幅" (price + 24h % change). Only `last_close` is shown.
17. **Indicator panels are 160px tall** — too short to read on Retina. The candle chart is 420px which is fine, but stacking 6+ panels of 160px makes scanning multiple at once impossible.
18. **No price tooltip on chart hover.** Lightweight Charts gives you crosshair-on-hover for free but no panel reads the synced time and shows "RSI=46.2 on 2026-04-12." Time-axis sync is technically complete but information-poor.
19. **`<details>` "Show 6 more indicators" creates a height jump** — when opened, the page scrolls awkwardly because all 6 charts mount at once with no skeleton.
20. **Backtest panel has no "fast/slow input" — fixed at (5,20)** even though the API supports overrides.
21. **Rank list highlights green for any value** — `rank-score` is hardcoded `--accent-green` even when displaying reversal scores (where the semantic is mean-reversion, not bullish trend).
22. **Mobile / narrow-screen:** breakpoint at 900px is generous (good) but the candle chart never resizes — it's set to `container.clientWidth` once at create-time and `ResizeObserver` is never wired. A user dragging the window or rotating their iPad gets a clipped chart.
23. **Empty / loading state is just `--`** — no skeleton, no spinner, no "loading bitcoin chart..." text. The first 500ms on token-change show six empty rectangles.
24. **First-time user has no idea what this is.** Page title says "IOSG Crypto Tech Dashboard" — no sub-heading, no "what this measures," no example of how to use it. The "5-second test" fails for anyone outside IOSG.

---

## Plan gaps (Plan describes → code doesn't have)

- **Search-enabled token selector** (Plan §7.3) — not implemented (raw `<select>` with no `<datalist>` either).
- **Per-panel parameter override UI with 300ms debounce + reset** (Plan §7.3) — not implemented.
- **Golden-cross / death-cross / event markers on charts** (Plan §4.1 step 9-10, §7.1 row "金叉死叉三角") — backend returns the boolean series, frontend ignores them.
- **Volume bars with spike highlighting on the Volume-Spike panel** (Plan §4.8, §7.1) — replaced by a single ratio line.
- **Sparkline next to each entry in the ranking sidebar** (Plan §7.3) — not implemented.
- **"Last updated 3 hrs ago" relative time + status indicator** (Plan §6, §7.1 header row) — only a raw ISO timestamp is shown.
- **Refresh polling against `/api/system/status` until `idle`** (Plan §7.3) — replaced by a 5-second blind `setTimeout`.
- **"仅收盘价数据" badge for fallback tokens** (Plan §3.1.2) — not implemented in UI; the `/api/tokens` payload doesn't even expose the source field.
- **Real 2y/3y historical percentile** (Plan §5.3) — exists in code but is degenerate because only ~300 days of history were loaded.
- **`scores_history.csv` persistence** (Plan §3.2 step 5) — not present in `local_data/`; the historical percentile is recomputed on-the-fly using a *different formula* than the headline score.
- **Mobile-first detail: sidebar becomes a "底部可拉起抽屉" on mobile** (Plan §7.3) — sidebar instead just stacks below at <900px.
- **`/api/data-check` endpoint** (Plan §8) — route does not exist; returns 404.
- **SVG gauge for trend/reversal scores** (Plan §7.1) — replaced by plain numeric display.
- **Score history sparkline / time-series chart** (Plan §5.3 implicit) — not implemented; user can't see trajectory of a token's trend score over the last 90 days.

---

## PM additions (not in Plan but recommended for v1)

- **Plain-English score legend ("What is Trend Score?")** — a one-paragraph collapsible explainer with the 9 signals enumerated.
- **Mouse-over tooltips on every component value** — "rsi_dist_os_14 = (30 − RSI(14)) / 30. Positive when oversold."
- **Comparative anchor on score:** show the *median Trend* across the universe (e.g., "BTC 48.8 vs universe median 50.2") so the user knows what "normal" is.
- **HODL benchmark on the backtest panel** — the value of "SMA(5/20) golden cross" is *relative to buy-and-hold*; without the benchmark the absolute CAGR is meaningless.
- **Cross-sectional histogram for trend & reversal** — a sparkline at the top of the page showing the distribution of all 200 scores would tell the user instantly whether the market is in a bullish or bearish regime today.
- **"Movers in score" widget** — top 5 tokens whose trend rank rose / fell the most vs yesterday. This is the actionable insight a screener should provide; right now the only way to surface it is to manually load and compare snapshots.
- **Sector / category metadata** from CoinGecko (`categories[]`) — enables filtering rankings by L1 / DeFi / AI / RWA. CoinGecko Pro returns this for free.
- **CSV export of rankings** — a screener's users will want to paste into Sheets.
- **Permalink per token** — `?token=bitcoin` so the user can share or bookmark.
- **Keyboard navigation** — `↑/↓` in the sidebar to walk the ranking, `Enter` to load.
- **Error toast** — `console.error(e)` after a failed `/api/refresh` is the only feedback today.

---

## Recommended next 3 product moves

1. **Fix the data foundation first.** Diagnose why the OHLCV history capped at ~300 days (likely `limit=300` on the CCXT call in the fetcher loop). Re-run full load with `days=1095`, persist `scores_history.csv` as Plan §3.2.5 specified, and unify the historical-percentile formula with the headline cross-sectional formula so the two numbers live on the same axis. **Without this, the marquee "current vs own history" feature is broken-by-design.**
2. **Ship a credible ranking sidebar.** This is the entry-point to the product. Add: symbol + name (drop `cg_id`), 24h price change, current trend / reversal scores side-by-side, sector tag, mcap rank, sparkline of the last 30-day score trajectory, a search box, and a sort dropdown that includes "biggest mover today." This is one focused frontend sprint that doubles the product's perceived value.
3. **Make indicators self-explanatory.** Per-panel: a title, a legend, hover tooltips with values at the crosshair date, event markers (golden cross triangles, KDJ crosses, volume spikes), and one-sentence "what this means" text. Add a parameter input (period / fast / slow) wired to the existing `?fast=&slow=` API. Until the charts are readable without a code-reading session, this is a wall of squiggles.

---

## Uncertainties documented

- I did not load the UI in Chrome — review based on static analysis of `index.html`, `app.js`, `api.js`, `styles.css`, `candle.js`, `indicator_panels.js`, and live API probes. A visual pass might surface additional layout issues but should not change the punch list above.
- The 300-day cap is inferred from CSV row counts (BTC, ETH, SOL all = 301 rows including header). The fetcher source file (`backend/data/fetcher.py`) was not opened to confirm root cause; my recommendation is to inspect the `days` param actually passed to `ExchangeOHLCVClient.fetch_ohlcv`.
- `trend_score = 48.8` with `cs_percentile = 38.5` is consistent because `trend_score` is itself the cross-sectional percentile of the raw signal sum — but the labeling makes them look like different metrics. This is a naming issue not a math issue.
- The 33 fallback tokens may actually have legitimate exchange OHLCV (the "fallback" label might mean "lookup fell back to CCXT's secondary exchange," not "CoinGecko close-only"). I checked one file (`adi-token.csv`) which had `source=coingecko` rows, confirming at least some are truly close-only. Worth a backend sanity pass.
