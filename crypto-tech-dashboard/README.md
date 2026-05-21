# IOSG Crypto Tech Dashboard

A FastAPI + vanilla-JS dashboard that pulls the CoinGecko Top-200 daily OHLCV
through a Binance / OKX / Bybit / Gate.io waterfall, computes 12 technical
indicator families, and ranks every token by a blended trend / reversal
score plus 2-year and 3-year time-series percentiles.

## 1. One-time setup

```bash
# from inside crypto-tech-dashboard/
./scripts/setup.sh
```

The setup script:

- Creates `venv/` (uses `python3` by default; override with `PYTHON=python3.12`).
- Installs `requirements.txt`.
- Copies `.env.example -> .env` if missing.
- Makes `logs/`.

Then edit `.env` and replace `COINGECKO_API_KEY` with your real CoinGecko Pro key.

## 2. Run

```bash
./run.sh                # 127.0.0.1:8080 (default)
./run.sh --public       # 0.0.0.0:8080 (LAN-accessible)
./run.sh --port 9000
```

Then open `http://localhost:8080/` in any modern browser.

The first cold launch with no data is empty. To populate Top-200 OHLCV:

```bash
# from another shell, with the server running
curl -X POST 'http://localhost:8080/api/system/refresh?full=true'
# wait ~7 min — progress is logged to the server console
```

A second launch reuses the existing CSVs and is near-instant. The daily
APScheduler tick (08:30 Asia/Shanghai by default) calls `run_daily_update`
which appends one new row per token.

## 3. macOS autostart (optional)

Install the LaunchAgent so the server boots on login and restarts on crash:

```bash
bash scripts/install_launchd.sh
```

Logs go to `logs/uvicorn.{out,err}.log`. To uninstall:

```bash
launchctl unload -w ~/Library/LaunchAgents/com.iosg.crypto-dashboard.plist
rm ~/Library/LaunchAgents/com.iosg.crypto-dashboard.plist
```

## 3.1 Move to another laptop (green folder)

The whole `crypto-tech-dashboard/` directory is portable. Use the
included packer to produce a zip that excludes the venv, git history,
and rotation backups — and that redacts the CoinGecko key.

```bash
bash scripts/pack_green_folder.sh
# writes dashboard_green_YYYYMMDD.zip in the project root
```

On the destination machine:

```bash
unzip dashboard_green_20260514.zip -d crypto-tech-dashboard
cd crypto-tech-dashboard
$EDITOR .env       # set COINGECKO_API_KEY to your own Pro key
bash scripts/setup.sh
./run.sh
```

Everything in `local_data/ohlcv/`, `local_data/market_cap/`, and
`local_data/metadata/` ships intact, so the destination machine has the
full price history on first launch — no waiting for a cold reload.

## 3.2 Docker run (portable, no local Python required)

Goal: zip the whole `crypto-tech-dashboard/` folder, copy to another Mac
that has Docker Desktop installed, and start with two commands.

**`.env` handling — important:** the `.env` lives **inside the folder**
and travels with the zip. It is read at *runtime* by `docker compose`
(`env_file: .env`), NOT baked into the Docker image (the `.dockerignore`
excludes it from the build context). So:

- ✅ Putting `.env` inside the zip and shipping to a trusted teammate's
  Mac is safe — only the runtime container reads it.
- ❌ Don't publish the resulting Docker image publicly (it doesn't
  contain `.env`, but better safe than sorry).
- ❌ Don't post the zip to a public repo / public S3 bucket — the
  CoinGecko Pro key inside `.env` would leak.

What the `.dockerignore` excludes from the **build context** (kept out
of the image): `.env`, `venv/`, `.git/`, logs, caches,
`ohlcv_backup_*/`, the 47MB indicator pickle cache.

What `docker-compose.yml` does at **runtime**:

- `env_file: .env` reads the host folder's `.env` and injects vars.
- `volumes: ./local_data:/app/local_data` mounts the host data folder
  so daily-cron updates persist on the host (not lost on container restart).
- `ports: 8000:8000` maps the container port to the host.

**On the destination Mac (one-time setup):**

1. Install Docker Desktop (`brew install --cask docker` or download from docker.com).
2. Unzip the folder somewhere convenient.
3. `cd crypto-tech-dashboard/`
4. Verify `.env` is present (it should be — it's in the zip).
5. Run:
   ```bash
   docker compose up -d --build
   ```
   First build takes ~3-5 min (pulls Python 3.12-slim, installs requirements,
   copies code + seed data). Subsequent starts < 5 sec.
6. Open `http://localhost:8000` in any browser on the same Mac.

**Day-to-day commands:**

```bash
docker compose up -d           # start (uses last build)
docker compose logs -f dashboard   # tail logs
docker compose restart         # pick up code change after rebuild
docker compose down            # stop + remove container
docker compose up -d --build   # rebuild after code change
```

**Letting teammates access it (across networks):** the container only
listens on `localhost:8000`. To share, use one of the methods in the
"network sharing" section (Cloudflare Tunnel / Tailscale / etc.).

### 3.2 Admin endpoints (localhost-only)

Two admin endpoints guarded by a 127.0.0.1 / localhost / ::1 client check:

- `GET  /api/admin/integrity` — returns the last boot integrity check
  log (auto-quarantined corrupt files, stale tokens, validate_ohlcv
  issues per token).
- `POST /api/admin/repair/{cg_id}` — re-fetches one token via the full
  exchange waterfall + CoinGecko fallback and atomically writes the CSV.
  Use after a CSV is quarantined or when one token went stale.

```bash
curl -s http://localhost:8080/api/admin/integrity | jq
curl -s -X POST http://localhost:8080/api/admin/repair/bitcoin | jq
```

Requests from non-loopback addresses return 403.

## 4. Project layout

```
backend/                Python 3.12 FastAPI app
    main.py             entrypoint (lifespan + APScheduler 08:30 daily)
    config.py           .env + env-var loader (no hardcoded keys)
    data/               exchange_client, coingecko_client, symbol_mapping,
                        local_store, fetcher, data_validator
    indicators/         12 indicator families + base + registry
    scoring/            trend_score, reversal_score, ranking (TS + CS %iles)
    backtest/           golden_cross (equity curve + stats)
    services/           data_service (the singleton view-layer cache)
    api/                routes_* — every endpoint listed in PLAN §8
frontend/               static SPA (no build step)
    index.html
    css/styles.css      TradingView dark theme
    js/
        api.js          fetch wrapper
        app.js          main controller
        components/     score_gauge.js, sparkline.js
        charts/         candle.js, indicator_panels.js
    lib/lightweight-charts.standalone.production.js   (v4.2.0, pinned)
local_data/             local CSV cache (CoinGecko id keyed)
    ohlcv/              one CSV per token
    market_cap/         top200_current.csv + scores_history.csv
    metadata/           symbol_map.json, last_update.json,
                        cg_offset.json, data_integrity_log.json
    ohlcv_backup_*/     rotated full-load snapshots (kept N=3)
scripts/
    setup.sh            one-shot install
    full_initial_load.py        Top-200 + 3-year cold start (~7 min)
    backfill_scores_history.py  reconstruct historical trend/reversal series
    backfill_mcap_daily.py      reconstruct market_cap_daily.csv
    install_launchd.sh          macOS autostart installer
    com.iosg.crypto-dashboard.plist.template
    smoke_*.py                  smoke tests by layer
    integration_test.py         end-to-end happy path
run.sh                  thin uvicorn launcher
requirements.txt
.env.example
```

## 5. API surface

See `PLAN_技术指标Dashboard.md` §8 for the canonical list. Quick reference:

| Method | Path | Notes |
|--------|------|-------|
| GET    | `/api/tokens`                              | list all tracked tokens |
| GET    | `/api/tokens/{cg_id}`                      | one token + last close + close-only flag |
| GET    | `/api/ohlc/{cg_id}?days=365`               | K-line OHLCV |
| GET    | `/api/indicators/{cg_id}?days=365`         | all 12 families |
| GET    | `/api/indicators/{cg_id}/{family}?days=365&fast=5&slow=20` | one family with param overrides (P2-1) |
| GET    | `/api/sparklines?ids=a,b,c&days=30`        | batch close series for sidebar (P2-3) |
| GET    | `/api/scores`, `/api/scores/{cg_id}`       | trend/reversal + CS%ile + 2y/3y TS%ile |
| GET    | `/api/rankings?sort_by=trend&limit=20`     | sidebar feed |
| GET    | `/api/backtest/{cg_id}?fast=5&slow=20`     | golden-cross stats + equity_curve |
| GET    | `/api/system/status`, `/api/system/health` | server + last-run summary |
| POST   | `/api/system/refresh?full=false`           | trigger daily update; full=true for cold reload |

## 6. Operational notes

- **Geo-blocked exchanges.** From mainland China / Hong Kong, Binance returns
  HTTP 451 and Bybit 403. The waterfall transparently falls through to OKX
  and Gate.io; expect ~32-40 tokens to fall through further to the
  CoinGecko close-only fallback. These are flagged `close_only_data: true`
  in `/api/tokens/{id}` and the UI shows a "Close-only data" badge.
- **CoinGecko key rotation.** Set `COINGECKO_API_KEY` in `.env`. The server
  will refuse to construct the CoinGecko client if it is empty — there is
  no hardcoded fallback (P1-A).
- **Data backup.** A full reload snapshots the previous `ohlcv/` to
  `ohlcv_backup_YYYYMMDD/` and keeps the last 3 (P0-M). For DR, rsync
  `local_data/` to another disk or private storage once a week.
- **scores_history.csv.** This file is the 2y/3y time-series percentile
  backbone. If you blow it away, re-run `python scripts/backfill_scores_history.py`
  to reconstruct it from existing OHLCV; the cold reconstruct takes 5-15 min.

## 7. Smoke checks (read these first when something is wrong)

```bash
./run.sh                                       # server up?
curl -s localhost:8080/health                  # {"ok": true}
curl -s localhost:8080/api/system/status | jq
curl -s 'localhost:8080/api/scores?limit=5' | jq
curl -s 'localhost:8080/api/indicators/bitcoin/rsi?period=14' | jq '.params'
```

Frontend: open `localhost:8080/` and verify:

- Token combobox suggests on type (search by symbol / name / id).
- Candle chart fills the upper panel; six indicator panels below render.
- Trend / Reversal gauges show numeric values.
- Sidebar Top 20 has rank, symbol, sparkline, score.
- Refresh button polls until the daily update completes.

## 8. Known scope-deferred items

- **Mobile drawer.** Sidebar collapses below 900px width but is not yet
  a slide-up drawer.
- **CoinGecko T+1 detection** writes to `data_integrity_log.json` but the
  scoring layer does not yet shift CG-fallback rows; in practice they are
  close-only and don't carry indicator weight (NaN-guarded).
- **Score-component label humanisation.** The breakdown lists currently
  show `mom_ret_10d` etc. verbatim. A label-map dict is the smallest fix
  but is non-blocking for shipping.
