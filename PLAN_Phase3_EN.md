# Phase-3 Plan — Modification List (Based on Four Independent Audits)

> Translated from `三期Plan-修改清单.md`. This is the Phase-3 modification list (8 modules based on four independent role audits).

> **Written**: 2026-05-18
> **Baseline**: commit `b96f7e3` (Phase-2 completion + Docker + Milan UI fine-tuning)
> **Audit sources**: four independent audits from a quant engineer / senior analyst / Milan designer / Google PM
> **Principles**: Plan is written in Chinese; **all user-facing UI is entirely in English**; the mathematical core is left untouched (explicit user decision)
> **Estimated effort**: 4-5 working days
> **Target delivery track**: Track B — internal + IOSG portfolio controlled demos + LP roadshow

---

## Part 0 — Decision Premises (Already Decided by the User)

| Topic | User Decision |
|---|---|
| Trend sleeve 5d reverses direction (ρ=-0.014) | **Do not change the weight; do not say "significantly reversed"** — keep Tier-A 0.40 weight as "advisory data" |
| Should we call it a "machine learning model"? | **No** — it is currently just a linear fit; the copy must not imply ML |
| 1-2s token loading lag | **Leave it for now** — current compute is light; do not add a loading skeleton |
| Entry gate | **Add a password page**, password hard-coded as `IOSG` (uppercase); anyone who enters it gets in, no username |

---

## Part 1 — Eight Modification Modules (by priority)

### Module 1: Entry password page (authentication gate)

**Requirement**: Anyone who opens the dashboard first sees a password input page. Password is hard-coded `IOSG` (4 uppercase letters). After correct entry, store a token in localStorage; permanent until the user clears their browser cache.

**Files to change**:
- New `frontend/login.html` — full-screen password page, IOSG logo + input box + Enter to submit
- New `frontend/css/login.css` — minimalist style (black background, large type, TradingView login-page style)
- New `frontend/js/auth.js` — `localStorage.getItem('iosg-auth')` validation + `sessionStorage` fallback
- Modify `frontend/index.html` — add an inline auth-guard script at the top: not logged in → `location.href = '/login.html'`
- Modify `backend/main.py` — add `/login.html` route (static file serve); consider whether the backend `/api/*` also needs a token check (**v1 only blocks on the front end; the backend is not blocked — simple, sufficient for the demo scenario**)

**UI copy (English)**:
```
┌──────────────────────────────┐
│                              │
│          IOSG                │
│   Crypto Tech Dashboard       │
│                              │
│  ┌────────────────────┐      │
│  │ Enter access code  │      │
│  └────────────────────┘      │
│                              │
│       [  Enter  ]            │
│                              │
│   Internal preview ·         │
│   Not investment advice      │
└──────────────────────────────┘
```

**Acceptance**:
- After clearing browser localStorage, visiting `/` → redirects to `/login.html`
- Entering `IOSG` → jumps back to `/`; dashboard loads normally
- Wrong entry (lowercase `iosg` / other characters) → input box shakes + "Incorrect code" hint
- After successful entry, close the browser and reopen → no need to re-enter

**Effort**: 0.5 day

---

### Module 2: Legal footer (mandatory)

**Requirement**: A site-wide fixed footer containing the disclaimer + version number + data-delay note.

**Files to change**:
- Modify `frontend/index.html` — add a `<footer class="site-footer">` block after `</main>`
- Modify `frontend/css/styles.css` — `.site-footer` styling (sticky bottom, harmonized with the theme)

**UI copy (English, fixed)**:
```
┌─ Footer ──────────────────────────────────────────────────────────┐
│ © 2026 IOSG · v2.5.0 · Last data refresh: 2 hours ago            │
│                                                                    │
│ This dashboard is a research preview for internal IOSG and        │
│ portfolio-company use only. The displayed scores, rankings and    │
│ backtests are illustrative and DO NOT constitute investment       │
│ advice, solicitation, or a recommendation to buy or sell any      │
│ asset. Past performance does not guarantee future results.        │
│ Crypto and US-equity prices may be delayed.                       │
└────────────────────────────────────────────────────────────────────┘
```

**Acceptance**:
- Coordinated in both light and dark themes
- Text does not overflow at mobile viewport (375px)
- Version number is read from `package.json` or from the field returned by the backend `/api/system/health`

**Effort**: 1-2 hours

---

### Module 3: Automatic data refresh (system boot + daily at 9 AM)

**Requirement**: Two mechanisms layered together:
1. **Detection at system boot**: if `last_ohlcv_update` is not today, actively trigger a daily update (Yahoo + CCXT)
2. **Automatic refresh every morning at 9 AM Asia/Shanghai**: the existing APScheduler cron is currently 08:30 + 08:35; change to **09:00 + 09:05** to match the user expectation of "around 9 in the morning"
3. **Boot-time backfill**: if the data gap ≥ 2 days, automatically fill-the-gap rather than only fetching today

**Files to change**:
- Modify `backend/main.py` lifespan: at boot, read `last_update.json`, compare `today - last_ohlcv_update`; if ≥ 1 day, immediately run `run_daily_update` + `run_stocks_daily_update` in a background task
- Modify `backend/data/fetcher.py` `run_daily_update`: change lookback_days from 5 to `max(5, days_since_last_update + 2)` to cover multi-day gaps
- Modify `.env`: `UPDATE_HOUR=9`, `UPDATE_MINUTE=0`
- Modify `docker-compose.yml` / docs: update comments accordingly

**UI copy (English, topbar)**:
```
Current: "last update: 2026-05-15T16:25:27"   ← raw ISO, ugly
After:   "Updated 2 hours ago"                ← human-friendly
```
On mouse hover, show the full ISO timestamp (via `title=`).

**Obtaining the current time**:
- Frontend JS uses `new Date()` directly (browser local time, accurate enough)
- Backend uses `datetime.now(tz=ZoneInfo("Asia/Shanghai"))`
- **Do not call external public NTP APIs** — the server system clock is already synced via NTP; calling an external API is over-engineering

**Acceptance**:
- Deliberately change `last_update.json` to 3 days ago → start the service → backfill begins automatically within 5 seconds
- topbar time changes from ISO to "Updated X hours/minutes ago"
- The 9:00 morning cron actually fires (verify in logs)

**Effort**: 1 day

---

### Module 4: US stocks OHLC endpoint fix

**Requirement**: Currently `curl /api/ohlc/MSTR` returns 0 candle rows, but `local_data/ohlcv/MSTR.csv` does exist on disk. Endpoint bug.

**Investigation + fix steps**:
1. `curl http://127.0.0.1:8000/api/ohlc/MSTR` to see the actual response
2. Look at `backend/api/routes_ohlc.py` and find the `/api/ohlc/{cg_id}` handler
3. Most likely `validate_cg_id` rejects uppercase tickers, or `data_service.get_ohlcv` cannot find MSTR.csv
4. Likewise fix `/api/indicators/MSTR` if it is also broken

**Files to change**:
- Modify `backend/api/routes_ohlc.py` (or routes_indicators.py) — allow uppercase tickers through
- Modify `backend/services/data_service.py:get_ohlcv` — confirm the `local_data/ohlcv/{cg_id}.csv` lookup is compatible with uppercase

**Acceptance**:
- `curl /api/ohlc/MSTR?days=365` → ≥ 200 candles, from 2019-12-30 to today
- `curl /api/ohlc/COIN` / `CRCL` / `MARA` all work
- Frontend selects MSTR / COIN / CRCL → candlestick chart renders correctly

**Effort**: 2-4 hours

---

### Module 5: Unify asset_class naming

**Requirement**: The current code mixes `us-stock` / `stock` / `us_stock`; filters do not work.

**Investigation**:
```bash
grep -rn "asset_class" backend/ frontend/ | grep -E "stock|stocks"
```
Find every occurrence and unify them to **`us-stock`** (hyphenated, matching stocks_universe.csv).

**Files to change** (edit one by one after grep):
- `backend/services/data_service.py`
- `backend/api/routes_*.py`
- `frontend/js/app.js`
- `frontend/js/api.js`
- `frontend/index.html` (tab-btn data-tab)
- Any URL handler that contains a "stock" filter

**Acceptance**:
- `grep -rn "'stock'\|\"stock\"\|=stock\b" backend/ frontend/` → 0 hits (only us-stock allowed)
- `curl /api/scores?asset_class=us-stock` returns 38 stocks
- `curl /api/scores?asset_class=stock` returns empty (explicitly indicating the asset_class is wrong; no silent fallback)

**Effort**: 1-2 hours

---

### Module 6: Rewrite the quant-core disclaimer copy

**Requirement**:
- Tier-A 0.40 trend weight stays unchanged
- Do not mention "significantly reversed" in any form
- Remove any "machine learning" / "AI" implications → replace with "linear-weighted" / "rule-based"
- But **keep** the honest labeling of Tier-B / Calibrated — they are research experiments, and `accept=false` is an honest result

**Files to change**:
- `frontend/js/app.js renderTierBBanner()` — rewrite the banner copy
- `frontend/index.html` — rewrite any info-mark tooltip containing "ML" / "machine learning"
- `backend/scoring/explainers.py` — the strengths/weaknesses in the TREND/REVERSAL/OVERALL explainer must not mention "reversed direction"
- `README.md` — remove any "ML scoring" / "AI" wording

**Examples of UI copy rewrite**:
```
Current banner: "Theory weights · research-only (Sharpe 5d: theory -0.16 vs cal 0.07)"
After:          "Linear-weighted composite · research preview"

Current explainer Trend Weaknesses: "5d horizon Spearman is statistically reversed..."
After: "Optimized for multi-week to multi-month positioning; short-term swing
       signals are noisier. Cross-sectional ranking is universe-relative."
```

**Key principles**:
- Do not lie (do not say "AI-powered"), but also do not proactively expose the reversed-direction math (user decision)
- Position the focus on the **multi-week / multi-month** horizon
- "linear-weighted" is an accurate description and more honest than "AI"

**Acceptance**:
- grep "AI\|machine learning\|ML" frontend/ README.md → 0 hits (or only in internal docs/scoring_audit/)
- The banner shows no negative Sharpe numbers
- But the `/api/scoring/tier_b` + `/api/scoring/calibrated` endpoint data remains complete (internal researchers can still GET it)

**Effort**: 2-3 hours

---

### Module 7: Visual polish (Milan designer, 5 items)

**Requirement**: The Milan designer scored it 59/80 and listed 5 concrete changes that would push the score to →64+, into the LP tier.

#### 7.1 — Desaturate the 5 accents to a common source
- The current 5 accents jump from 47% to 100% saturation, not unified
- Modify `frontend/css/styles.css :root` + the light-theme block so that all 5 accents sit within HSL S=60-75%

**Example** (illustrative only; designer to fine-tune):
```css
/* before */
--accent-green: #26a69a;   /* S=62%, OK */
--accent-red:   #ef5350;   /* S=83%, too high */
--accent-yellow:#f7c948;   /* S=92%, too loud */
--accent-purple:#ab47bc;   /* S=53%, too low */

/* after — same-source saturation 60-75% */
--accent-green: #26a69a;
--accent-red:   #d85a58;
--accent-yellow:#d4ae3a;
--accent-purple:#9a4eb0;
```

#### 7.2 — Collapse the 12 indicator panels by default
- Currently all 12 panels are open; the first screen is suffocating
- On the first screen only expand 4: **SMA Cross / RSI / MACD / Bollinger**
- Move the other 8 into `.more-indicators <details>` (the structure already exists; just migrate them)

**Change**: re-order panel positions (DOM order) in `frontend/index.html`

#### 7.3 — Brand upgrade
- Current brand = `IOSG Crypto Tech Dashboard` 15px system font
- Change to two tiers:
  ```
  IOSG          ← 18px bold tabular-nums
  Tech Dashboard ← 11px upper-case letter-spaced
  ```
- Do not add an SVG logo (keep it minimal)

**Change**: topbar-left area of `frontend/index.html` + `.brand` in `frontend/css/styles.css`

#### 7.4 — Reversal badge: no purple
- Currently Reversal uses `--accent-purple` (purple)
- Change to neutral gray `--text-primary` digits + gray label
- Reserve purple for genuinely "purple" elements such as the KDJ J line

**Change**: `.score-badge.reversal span` in `frontend/css/styles.css`

#### 7.5 — Collapse font sizes to 5 tiers
- Currently 9/10/11/12/13/14/15/38/56 px scattered
- Unify to **5 tiers**: 10 / 12 / 14 / 38 / 56 (micro / caption / body / sub-hero / hero)
- Drop the intermediate values (9 → 10, 11 → 12, 15 → 14)

**Change**: globally grep `font-size: \d+px` in `frontend/css/styles.css` and normalize

**Acceptance**:
- On opening the homepage, the first screen has ≤ 4 indicator panels
- The 5 accents are harmonized in both dark / light themes (designer eyeballs it OR Python HSL diff)
- The brand looks like a finance tool, not a demo
- Reversal numbers are no longer purple

**Effort**: 1 day (Milan-aesthetic fine-tuning)

---

### Module 8: Patch items (corners flagged by the PM)

#### 8.1 — Friendly fallback for uppercase tokens in the URL
- Currently `/#token=ETH` (uppercase) silently falls back to BTC
- Change to: toast hint "Token 'ETH' not found; matched 'ethereum'" + auto-jump

**Change**: in `frontend/js/app.js init()`, add case-insensitive token matching + a hint

#### 8.2 — favicon + social meta tags
- Currently no favicon (browser tab shows the generic icon)
- Add an IOSG-letter favicon (16×16 + 32×32 PNG or SVG)
- `<meta property="og:title" content="IOSG Crypto Tech Dashboard">` and other social meta tags

**Change**: new `frontend/favicon.ico` + `frontend/index.html <head>`

#### 8.3 — `?token=ETH` uppercase matching
(Same as 8.1)

#### 8.4 — Error pages (404 / missing data)
- Pick a non-existent token id → currently may show a blank screen or hang
- Add a graceful empty state: "Token not found. Try BTC / ETH / SOL."

**Change**: error branch in `frontend/js/app.js selectToken` or `onTokenChange`

**Effort**: half a day

---

## Part 2 — Effort Summary + Priority

| Module | Effort | Priority | Blocker for LP demo? |
|---|---|---|---|
| 1. Password page | 0.5 day | P0 | ✓ Blocker |
| 2. Legal footer | 2 hours | P0 | ✓ Blocker |
| 3. Auto data refresh | 1 day | P0 | ✓ Blocker (stale-data issue) |
| 4. US stocks OHLC fix | 2-4 hours | P0 | ✓ Blocker (US stocks unusable) |
| 5. Unified asset_class naming | 1-2 hours | P1 | Corner |
| 6. Quant disclaimer copy | 2-3 hours | P0 | ✓ Blocker (public sees negative Sharpe) |
| 7. Visual polish, 5 items | 1 day | P1 | Not a blocker, but LP experience will suffer |
| 8. PM patch items, 4 items | 0.5 day | P2 | Nice-to-have |
| **Total** | **4-5 days** | | |

---

## Part 3 — Suggested Execution Order (Linear)

```
Day 1
├─ Morning:   Module 1 password page (0.5d)
└─ Afternoon: Module 2 footer (2h) + Module 6 quant disclaimer copy (3h)

Day 2
├─ Morning:   Module 3 auto data refresh (boot + cron + time display)
└─ Afternoon: Module 3 continued + testing

Day 3
├─ Morning:   Module 4 US stocks OHLC fix (2-4h) + Module 5 asset_class unification (1-2h)
└─ Afternoon: Module 7.1 + 7.2 accent + panel collapse

Day 4
├─ Morning:   Module 7.3 brand + 7.4 Reversal + 7.5 font sizes
└─ Afternoon: Module 8 PM patch items

Day 5
├─ Morning:   Combined smoke test + end-to-end acceptance (re-run the 4-party audit checklist)
└─ Afternoon: Commit and push + write the changelog
```

---

## Part 4 — Acceptance / Audit Checklist

Run these after finishing each module:

### General sanity
- [ ] Service starts with no errors
- [ ] All 17 endpoints return 200
- [ ] All 9 JS files pass syntax
- [ ] 0 Chinese characters in backend / frontend source
- [ ] Light + dark themes switch correctly

### Module 1 acceptance
- [ ] Clearing localStorage → auto-redirect to `/login.html`
- [ ] Entering `IOSG` → jump back to `/`
- [ ] Entering `iosg` / other → rejected + hint

### Module 2 acceptance
- [ ] Footer is harmonized in both light and dark
- [ ] Does not overflow at the 375px mobile viewport
- [ ] Version number is correct

### Module 3 acceptance
- [ ] Change last_update to 3 days ago and start → backfill within 5 seconds
- [ ] 9:00 morning cron fires
- [ ] Topbar time displays "Updated 2 hours ago"

### Module 4 acceptance
- [ ] `/api/ohlc/MSTR` returns ≥ 200 candles
- [ ] Frontend selects MSTR / COIN / CRCL → candlesticks render

### Module 5 acceptance
- [ ] `grep us_stock\|=stock\b` → 0 hits
- [ ] `?asset_class=us-stock` returns 38
- [ ] `?asset_class=stock` returns empty / errors (not silent)

### Module 6 acceptance
- [ ] grep "AI\|machine learning" frontend/ README → 0
- [ ] Banner copy "Linear-weighted composite · research preview"
- [ ] No negative Sharpe numbers exposed anywhere

### Module 7 acceptance
- [ ] All 5 accents have HSL S within 60-75%
- [ ] ≤ 4 indicator panels on the first screen
- [ ] Brand visually upgraded
- [ ] Reversal numbers no longer purple
- [ ] Only 5 font-size values globally

### Module 8 acceptance
- [ ] Favicon shows in the browser tab
- [ ] og:title meta exists
- [ ] `#token=ETH` uppercase → hint + jump to ethereum
- [ ] Selecting a non-existent token → no blank screen

---

## Part 5 — What We Are NOT Doing (Explicit Scope)

To avoid scope creep, this phase **does NOT do**:

- ❌ Change Tier-A 0.40 trend weight (user decided to keep)
- ❌ Expose the trend 5d reverse-direction warning in the UI (user decided not to mention)
- ❌ Expose survivorship bias in the UI (user did not explicitly request; wait for later)
- ❌ Tier-D point-in-time universe rebuild (Phase 3 backlog)
- ❌ Systematize rate-limit / auth (the password page is enough; no real user management)
- ❌ Backend token validation (frontend gating is enough; demo scenario does not need it)
- ❌ pytest CI suite (team will do it after handover)
- ❌ Loading skeleton (user decided to leave it for now)
- ❌ Sharpe / Calibrated math corrections (user decided to disclaim first, do not move weights)
- ❌ HK-stock universe (Phase 3 backlog)

---

## Part 6 — Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Module 3: 9:00 morning cron mismatches the host timezone | Medium | Data delay | Add `TZ=Asia/Shanghai` env in docker-compose |
| Module 4: the US stocks OHLC bug is more complex than expected | Low | Half a day extra | Debug time is buffered |
| Module 7: designer fine-tuning is subjective | Medium | Repeated revisions | First pass goes by the numbers hard-coded in this plan |
| Password `IOSG` is too weak and gets brute-forced | High (if public) | Zero security | Limit to controlled sharing; do not post on Twitter |
| The softened Tier-B banner copy hides honest information from internal researchers | Low | Loss of transparency | API endpoint keeps the full data; only the frontend banner is softened |

---

## Part 7 — Definition of Done

After executing this plan, the system has:

✅ **Entry gate**: password IOSG
✅ **Legal**: footer disclaimer + version number
✅ **Data**: self-starting auto-backfill + 9:00 morning cron + human-friendly time display
✅ **US stocks**: MSTR / COIN / CRCL candlesticks viewable
✅ **Naming**: asset_class unified to us-stock
✅ **Copy**: no mention of ML / reversed direction; positioned as "linear-weighted research preview"
✅ **Visual**: Milan designer's 5 items done, score 64+/80
✅ **Corners**: favicon / social meta / friendly fallback for uppercase tokens / no blank screen on 404

Ready to send to LPs / IOSG portfolio CTOs / controlled demos; not for Twitter / PH.

---

**Next step**: user reviews this plan → decides "start execution" → I execute module by module in the Day 1-5 order.
