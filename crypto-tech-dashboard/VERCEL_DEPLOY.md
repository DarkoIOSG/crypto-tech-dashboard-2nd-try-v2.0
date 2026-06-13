# Vercel Deployment Guide

## Architecture recap

```
GitHub Actions (free)
  └─ daily cron 09:00 Shanghai → runs scripts/run_daily_update.py
       → fetches OHLCV from CCXT + CoinGecko
       → writes to Neon Postgres

Neon Postgres (free tier, ~50–80 MB)
  └─ ohlcv, tokens, scores_history, scores_snapshot, metadata tables

Vercel Hobby (free)
  └─ FastAPI serverless function (api/index.py)
  └─ Reads from Neon on every request
  └─ In-memory cache per warm invocation
```

---

## Step 1 — Create a Neon Postgres database

1. Go to [neon.tech](https://neon.tech) and sign up for a free account.
2. Create a new project (any name, e.g. `iosg-dashboard`).
3. In the Neon console, open **Connection Details** and copy the **Pooler** connection string.
   It looks like:
   ```
   postgresql://user:password@ep-xxxx.pooler.neon.tech:5432/neondb?sslmode=require
   ```
4. Keep this string — you'll need it in both Vercel and GitHub Actions secrets.

---

## Step 2 — Seed the database from your Mac mini (one time only)

This copies all 248 token OHLCV files (~125 MB on disk, ~50 MB in Postgres) into Neon.

```bash
cd crypto-tech-dashboard-2nd-try-v2.0/crypto-tech-dashboard

# Install Python deps if you haven't yet
pip install -r requirements-fetcher.txt

# Run the migration (takes 2–5 minutes)
DATABASE_URL="postgresql://..." \
COINGECKO_API_KEY="cg_live_..." \
python scripts/migrate_to_postgres.py
```

You should see progress logs like:
```
Migrating 248 OHLCV files …
  25 / 248 files done (57832 rows so far)
  50 / 248 files done (115442 rows so far)
  ...
Wrote scores snapshot for 240 tokens
Migration complete.
```

---

## Step 3 — Deploy to Vercel

### Option A: Vercel CLI (recommended)

```bash
# Install Vercel CLI
npm install -g vercel

cd crypto-tech-dashboard-2nd-try-v2.0/crypto-tech-dashboard

# Link and deploy
vercel

# Set environment variables (Vercel Hobby: use the Vercel dashboard or CLI)
vercel env add DATABASE_URL
# paste your Neon pooler connection string when prompted

vercel env add COINGECKO_API_KEY
# paste your CoinGecko Pro key when prompted (needed for /api/system/refresh)
```

### Option B: Vercel Dashboard

1. Push this repo to GitHub.
2. Import it in [vercel.com/new](https://vercel.com/new).
3. Set the **Root Directory** to `crypto-tech-dashboard`.
4. Add environment variables:
   - `DATABASE_URL` → your Neon pooler string
   - `COINGECKO_API_KEY` → your CoinGecko Pro key
5. Deploy.

The `vercel.json` in `crypto-tech-dashboard/` tells Vercel to use `api/index.py` as
the serverless entry point, and `api/requirements.txt` as the slim dependency set.

---

## Step 4 — Set up GitHub Actions for daily refresh

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**.
2. Add two repository secrets:
   - `COINGECKO_API_KEY` — your CoinGecko Pro key
   - `DATABASE_URL` — your Neon pooler connection string
3. The workflow at `.github/workflows/daily_refresh.yml` fires automatically at
   01:00 UTC (= 09:00 Asia/Shanghai) every day.
4. To trigger it manually (e.g. after changing the token universe):
   - Go to **Actions → Daily Data Refresh → Run workflow**
   - Leave `full_load` as `false` for an incremental update

### Doing a full reload from scratch (new database)

If you've wiped the Neon database and need to reload everything:

1. Go to **Actions → Daily Data Refresh → Run workflow**
2. Set `full_load` to `true`
3. Click **Run workflow**

This runs `scripts/run_full_initial_load.py` which pulls ~6 years of OHLCV
for all 240 tokens directly into Neon. Expect 15–30 minutes.

---

## Step 5 — Verify it works

```bash
# Health check
curl https://your-app.vercel.app/health
# → {"ok": true}

# Scores (reads from Neon scores_snapshot — fast)
curl https://your-app.vercel.app/api/scores?limit=5 | jq

# OHLCV for one token (reads from Neon ohlcv table)
curl 'https://your-app.vercel.app/api/ohlc/bitcoin?days=30' | jq '.[-1]'

# Open the dashboard
open https://your-app.vercel.app
# Access code: IOSG
```

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes (Vercel)** | Neon Postgres pooler connection string |
| `COINGECKO_API_KEY` | **Yes** | CoinGecko Pro API key |
| `DATA_DIR` | No | Scratch dir for temp files (default: `./local_data`) |
| `HISTORY_DAYS` | No | Days of OHLCV history to keep (default: 2326 ≈ 6y) |
| `TOP_N` | No | Universe size (default: 200) |

---

## Cost breakdown (all free tiers)

| Service | Free tier | Usage |
|---|---|---|
| Vercel Hobby | Free | Frontend + API serverless |
| Neon Postgres | Free (0.5 GB storage) | ~50–80 MB OHLCV + metadata |
| GitHub Actions | Free (2000 min/month) | ~10 min/day = ~300 min/month |

**Total monthly cost: $0** (assuming CoinGecko Pro is already paid for).

---

## Switching back to Docker (if needed)

The Docker path is completely unchanged. Just run:

```bash
docker compose up -d --build
```

Do NOT set `DATABASE_URL` in `.env` for Docker — it will then use the local
CSV files as before. Both modes work from the same codebase.
