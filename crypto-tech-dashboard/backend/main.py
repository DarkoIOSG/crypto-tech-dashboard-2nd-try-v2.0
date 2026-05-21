"""FastAPI app entry — wires routes, scheduler, and frontend static mount.

try/except is permitted in this file's lifespan/scheduler boundary per the
hard rules (it's the only place we tolerate exceptions in the main process).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.api import (
    routes_admin,
    routes_backtest,
    routes_indicators,
    routes_market,
    routes_robustness,
    routes_scores,
    routes_scoring_meta,
    routes_system,
    routes_tokens,
)
from backend.config import (
    DATA_DIR,
    METADATA_DIR,
    PROJECT_ROOT,
    UPDATE_HOUR,
    UPDATE_MINUTE,
    UPDATE_TIMEZONE,
)
from backend.data.coingecko_client import CoinGeckoClient
from backend.data.data_validator import DataValidator
from backend.data.exchange_client import ExchangeOHLCVClient
from backend.data.fetcher import Fetcher
from backend.data.local_store import LocalStore
from backend.data.symbol_mapping import SymbolMapper
from backend.services.data_service import DataService, set_service


log = logging.getLogger("backend.main")


# ----------------------------------------------------------------- #
# App factory + lifespan
# ----------------------------------------------------------------- #

_scheduler: BackgroundScheduler | None = None
_fetcher: Fetcher | None = None


def _build_fetcher() -> Fetcher:
    exch = ExchangeOHLCVClient()
    cg = CoinGeckoClient()
    mapper = SymbolMapper(METADATA_DIR, exch)
    # R8-1A: honor DATA_DIR env var (was hardcoded to PROJECT_ROOT / "local_data"
    # which ignored .env override; broke the "green folder" portability story
    # documented in PLAN section 11.10 and the handover guide sec 6).
    store = LocalStore(DATA_DIR)

    # P0-L: wire the real DataValidator so the daily-update tail writes
    # local_data/metadata/data_integrity_log.json with the per-token
    # validate_ohlcv() + validate_top200() output. Previously a no-op
    # stub returned None and the file never existed.
    return Fetcher(
        exchange_client=exch,
        coingecko_client=cg,
        mapper=mapper,
        store=store,
        validator=DataValidator(store),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler, _fetcher

    # Initialise in-memory data service from disk.
    svc = DataService()
    svc.refresh_from_disk()
    set_service(svc)

    # R8-1A: boot-time integrity check. Walks every OHLCV CSV, flags
    # corruption / staleness, quarantines unreadable files to
    # DATA_DIR/quarantine/ and persists the full report to
    # DATA_DIR/metadata/data_integrity_log.json. Does NOT auto-repair —
    # quarantined tokens must be explicitly repaired via
    # POST /api/admin/repair/{cg_id} to avoid silently triggering 200
    # CG API calls on a misconfigured boot.
    try:
        from backend.data.integrity import verify_local_data_integrity
        integrity = verify_local_data_integrity()
        n_quar = len(integrity.get("quarantined", []))
        n_stale = len(integrity.get("stale", []))
        n_clean = integrity.get("clean", 0)
        n_total = integrity.get("total_files", 0)
        if n_quar > 0:
            log.warning(
                "integrity check: %d/%d clean, %d quarantined (manual repair needed), %d stale",
                n_clean, n_total, n_quar, n_stale,
            )
        else:
            log.info(
                "integrity check: %d/%d clean, %d stale",
                n_clean, n_total, n_stale,
            )
        # Reload svc so any quarantine moves are reflected.
        if n_quar > 0:
            svc.refresh_from_disk()
    except Exception as exc:  # noqa: BLE001 - lifespan boundary
        log.warning("integrity check failed: %s", exc)

    # Build fetcher and bind it to the refresh endpoint.
    try:
        _fetcher = _build_fetcher()
        routes_system.bind_fetcher(_fetcher)
        routes_admin.bind_fetcher(_fetcher)  # R8-1A: admin repair endpoint
        log.info("fetcher bound to /api/system/refresh and /api/admin/repair")
    except Exception as exc:  # noqa: BLE001 - tolerate boot-time issues
        log.warning("fetcher unavailable: %s", exc)
        _fetcher = None

    # P0-K: detect & persist the CoinGecko T+1 date offset relative to the
    # exchange UTC-midnight bar. Result is written to
    # local_data/metadata/cg_offset.json and read by
    # CoinGeckoClient.fetch_close_price_history on every call so the
    # close-only fallback path returns dates aligned with the rest of the
    # universe. Permitted try/except: lifespan boundary (hard rule c).
    try:
        if _fetcher is not None:
            payload = _fetcher.coingecko_client.validate_cg_offset(
                exchange_client=_fetcher.exchange_client, days=30
            )
            log.info(
                "cg_offset detected: offset_days=%s mean_abs_pct=%s",
                payload.get("offset_days"),
                payload.get("btc_max_diff_pct"),
            )
    except Exception as exc:  # noqa: BLE001 - lifespan boundary
        log.warning("validate_cg_offset failed: %s", exc)

    # R6-9: check that each exchange in the PLAN sec 3.1 priority chain
    # actually loaded markets. A 0-markets exchange is silently dropped
    # from the waterfall in production, which degrades data redundancy
    # (Round-6 Quant audit P1: Binance + Bybit returned 0 markets on the
    # audited host, so the effective chain was OKX → gateio → CG and 32
    # of 200 tokens fell to CG close-only — 6× PLAN's expected ~5).
    # Surface this loud at boot so operators notice; persist a per-
    # exchange `available: bool` map to last_update.json so the UI can
    # render a degradation badge alongside the fallback count.
    try:
        if _fetcher is not None:
            mkts = _fetcher.exchange_client.load_markets_all()
            health = {}
            unavailable: list[str] = []
            # R8-1B.1: iterate the full EXCHANGE_PRIORITY (8 names) rather
            # than the hard-coded 4-tuple; otherwise the boot health probe
            # would silently miss the 4 newly added exchanges.
            from backend.config import EXCHANGE_PRIORITY as _EX_PRI
            for name in _EX_PRI:
                m = mkts.get(name)
                count = len(m) if isinstance(m, dict) else 0
                health[name] = {
                    "available": count > 0,
                    "markets_count": count,
                }
                if count == 0:
                    unavailable.append(name)
            if unavailable:
                log.warning(
                    "exchange_health: %s returned 0 markets — likely geo-blocked or "
                    "API-changed; waterfall degrades to remaining providers and "
                    "CoinGecko close-only fallback may exceed PLAN sec 3.1 ~5-token "
                    "budget. Persisting status to last_update.json.",
                    ", ".join(unavailable),
                )
            else:
                log.info(
                    "exchange_health: all %d exchanges reachable (markets counts: %s)",
                    len(health),
                    {n: h["markets_count"] for n, h in health.items()},
                )
            # Merge into last_update.json so /api/system/status surfaces it.
            from backend.config import DATA_DIR
            import json as _json
            meta_dir = DATA_DIR / "metadata"
            meta_dir.mkdir(parents=True, exist_ok=True)
            lu_path = meta_dir / "last_update.json"
            existing: dict = {}
            if lu_path.exists():
                try:
                    existing = _json.loads(lu_path.read_text() or "{}")
                except Exception:
                    existing = {}
            existing["exchange_health"] = health
            tmp = lu_path.with_suffix(".json.tmp")
            tmp.write_text(_json.dumps(existing, indent=2, sort_keys=True))
            tmp.replace(lu_path)
            # R6-9 bug-fix: svc.last_update was populated by refresh_from_disk()
            # BEFORE this probe wrote exchange_health, so the in-memory copy
            # would have stayed stale until the next mcap update.
            # Patch the new field into the live svc so /api/system/status
            # exposes it immediately on this boot.
            svc.last_update["exchange_health"] = health
    except Exception as exc:  # noqa: BLE001 - lifespan boundary
        log.warning("exchange_health probe failed: %s", exc)

    # APScheduler — daily crons in Asia/Shanghai.
    # Phase 3 Module 3: boot-time data freshness check. If last_ohlcv_update
    # is ≥ 1 day old (laptop was off, container was down, etc.), fire a
    # background daily-update + stocks-update RIGHT NOW so the user doesn't
    # see stale data on the first page load. The update runs in a thread so
    # the server still becomes ready in <1s for /api/* requests.
    try:
        if _fetcher is not None:
            from datetime import datetime as _dt_now, timedelta as _td
            last = _fetcher.store.read_last_update() or {}
            # Phase 3.3 (architect final audit): check BOTH crypto and stocks
            # timestamps. Previously gated on last_ohlcv_update alone — if
            # crypto stayed fresh but stocks died for 3 days, the boot
            # freshness check would silently skip both. max(crypto_gap,
            # stocks_gap) catches stocks-only staleness too.
            def _gap_days_for(key):
                iso = last.get(key)
                if not iso:
                    return None
                try:
                    dt = _dt_now.fromisoformat(iso.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        return (_dt_now.now() - dt).days
                    return (_dt_now.now(dt.tzinfo) - dt).days
                except Exception:
                    return None
            crypto_gap = _gap_days_for("last_ohlcv_update")
            stocks_gap = _gap_days_for("last_stocks_update")
            candidate = [g for g in (crypto_gap, stocks_gap) if g is not None]
            if candidate:
                stale_days = max(candidate)
            elif last.get("last_ohlcv_update") or last.get("last_stocks_update"):
                # have a timestamp but parsing failed
                stale_days = None
            else:
                stale_days = 9999  # never updated → treat as very stale

            if stale_days is None:
                log.info("boot freshness check: no parsable last_ohlcv_update; skipping auto-refresh")
            elif stale_days >= 1:
                log.info(
                    "boot freshness check: data is %d day(s) stale — triggering "
                    "background auto-refresh (crypto + stocks)", stale_days,
                )
                import threading as _threading
                def _bg_refresh():
                    try:
                        _fetcher.run_daily_update()
                    except Exception as e:  # noqa: BLE001
                        log.warning("auto-refresh crypto failed: %s", e)
                    try:
                        _fetcher.run_stocks_daily_update()
                    except Exception as e:  # noqa: BLE001
                        log.warning("auto-refresh stocks failed: %s", e)
                    log.info("boot auto-refresh: complete")
                _threading.Thread(target=_bg_refresh, daemon=True,
                                  name="boot-auto-refresh").start()
            else:
                log.info("boot freshness check: data is fresh (%d day(s) old)", stale_days)
    except Exception as exc:  # noqa: BLE001
        log.warning("boot freshness check failed: %s", exc)

    # R8-1D: separate cron for stocks 5 min after crypto so they don't
    # share state. yfinance US data updates ~04:00 Asia/Shanghai the
    # following morning (post US close 16:00 ET), so a 08:35 pull always
    # has yesterday's complete bar.
    try:
        # P0-1 (architect audit): without misfire grace, APScheduler silently
        # drops any cron fire that lands while the host is asleep — the Mac
        # mini sleeping through 09:00 means daily_update is lost until the
        # next *successful* 09:00 fire. With a 6-hour grace + coalesce=True,
        # waking up at e.g. 14:00 will catch up the missed 09:00 fire exactly
        # once (coalesce collapses any duplicate fires). max_instances=1 also
        # acts as a free in-process lock for scheduler-triggered runs so two
        # jobs of the same id can never overlap.
        _scheduler = BackgroundScheduler(
            timezone=UPDATE_TIMEZONE,
            job_defaults={
                "coalesce": True,
                "misfire_grace_time": 6 * 3600,
                "max_instances": 1,
            },
        )
        if _fetcher is not None:
            _scheduler.add_job(
                _fetcher.run_daily_update,
                CronTrigger(
                    hour=UPDATE_HOUR, minute=UPDATE_MINUTE, timezone=UPDATE_TIMEZONE
                ),
                id="daily_update",
                replace_existing=True,
            )
            # R8-1D: stocks daily refresh (US tickers via yfinance).
            stocks_minute = (UPDATE_MINUTE + 5) % 60
            stocks_hour = UPDATE_HOUR + ((UPDATE_MINUTE + 5) // 60)
            _scheduler.add_job(
                _fetcher.run_stocks_daily_update,
                CronTrigger(
                    hour=stocks_hour, minute=stocks_minute, timezone=UPDATE_TIMEZONE
                ),
                id="stocks_daily_update",
                replace_existing=True,
            )

            # Phase 3.1 fix: hourly self-heal. If the host machine was
            # asleep at 09:00 / 09:05, or APScheduler skipped a fire for
            # any reason, the daily refresh would never recover until a
            # full container restart. Check every hour on the :30; if
            # last_ohlcv_update is >= 1 day stale, trigger the daily +
            # stocks updates inline. Cheap when fresh (read 1 json file),
            # auto-recovers when stale.
            # P0-4 (architect audit): cooldown so a permanently-stale state
            # (e.g. network blocked / CG API key revoked) doesn't fire the
            # self-heal every hour and burn the CG quota in 6-8 hours. Track
            # the wall-clock of the previous self-heal attempt and skip if
            # within 4 hours. The 09:00 cron is unaffected.
            _self_heal_last_attempt = {"ts": 0.0}

            def _hourly_self_heal():
                try:
                    import time as _time_h
                    from datetime import datetime as _dt_h
                    last = _fetcher.store.read_last_update() or {}
                    # Phase 3.3 (architect final): check BOTH timestamps.
                    # Previously stocks-only staleness was invisible because
                    # gate only watched last_ohlcv_update.
                    def _gap_h(key):
                        iso = last.get(key)
                        if not iso:
                            return None
                        try:
                            dt = _dt_h.fromisoformat(iso.replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                return (_dt_h.now() - dt).total_seconds() / 86400
                            return (_dt_h.now(dt.tzinfo) - dt).total_seconds() / 86400
                        except Exception:
                            return None
                    crypto_g = _gap_h("last_ohlcv_update")
                    stocks_g = _gap_h("last_stocks_update")
                    gaps = [g for g in (crypto_g, stocks_g) if g is not None]
                    if not gaps:
                        return
                    gap_days = max(gaps)
                    if gap_days >= 1.0:
                        # P0-4: cooldown check.
                        now_ts = _time_h.time()
                        since_last = now_ts - _self_heal_last_attempt["ts"]
                        if since_last < 4 * 3600:
                            log.info(
                                "hourly self-heal: data is %.1f day(s) stale but "
                                "last attempt was %.1f h ago — cooldown, skipping",
                                gap_days, since_last / 3600,
                            )
                            return
                        _self_heal_last_attempt["ts"] = now_ts
                        log.warning(
                            "hourly self-heal: data is %.1f day(s) stale — triggering refresh",
                            gap_days,
                        )
                        try:
                            _fetcher.run_daily_update()
                        except Exception as e:  # noqa: BLE001
                            log.warning("self-heal crypto failed: %s", e)
                        try:
                            _fetcher.run_stocks_daily_update()
                        except Exception as e:  # noqa: BLE001
                            log.warning("self-heal stocks failed: %s", e)
                except Exception as exc:  # noqa: BLE001
                    log.warning("hourly self-heal check failed: %s", exc)

            _scheduler.add_job(
                _hourly_self_heal,
                CronTrigger(minute=30, timezone=UPDATE_TIMEZONE),  # every hour on the :30
                id="hourly_self_heal",
                replace_existing=True,
            )
        _scheduler.start()
        log.info(
            "scheduler started — daily_update @ %02d:%02d %s, stocks @ %02d:%02d %s",
            UPDATE_HOUR, UPDATE_MINUTE, UPDATE_TIMEZONE,
            (UPDATE_HOUR + ((UPDATE_MINUTE + 5) // 60)) if _fetcher else UPDATE_HOUR,
            (UPDATE_MINUTE + 5) % 60,
            UPDATE_TIMEZONE,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("scheduler init failed: %s", exc)
        _scheduler = None

    yield

    # Shutdown
    try:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
    except Exception:
        pass


# ----------------------------------------------------------------- #
# Build the app
# ----------------------------------------------------------------- #
app = FastAPI(title="IOSG Crypto Tech Dashboard", lifespan=lifespan)


# Routes
app.include_router(routes_tokens.router)
app.include_router(routes_indicators.router)
app.include_router(routes_scores.router)
app.include_router(routes_backtest.router)
app.include_router(routes_system.router)
app.include_router(routes_admin.router)  # R8-1A: localhost-only admin endpoints
app.include_router(routes_market.router) # R8-1C: market overview
app.include_router(routes_robustness.router) # R8-2B: indicator robustness
app.include_router(routes_scoring_meta.router) # R8-2C: score explainers


# Health check (the simple /health is part of the smoke gate).
@app.get("/health")
def health():
    return {"ok": True}


# Static frontend mount at "/".
FRONTEND_DIR = Path(PROJECT_ROOT) / "frontend"
if FRONTEND_DIR.exists():
    # Serve the SPA index at /, and all assets at the matching paths.
    @app.get("/")
    def index():
        idx = FRONTEND_DIR / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return JSONResponse({"error": "frontend index.html missing"}, status_code=404)

    # Phase 3 Module 1: serve the access-gate login page. The dashboard
    # index.html has an inline guard that redirects here when the user
    # has not yet entered the access code.
    @app.get("/login.html")
    def login_page():
        page = FRONTEND_DIR / "login.html"
        if page.exists():
            return FileResponse(str(page))
        return JSONResponse({"error": "login.html missing"}, status_code=404)

    # Browser favicon. Avoids the 404 noise in the access log.
    # Phase 3 Module 8 (PM): always return a 1x1 transparent PNG when the
    # repo has no real .ico. Some browsers ignore the inline SVG <link>
    # and still hit /favicon.ico; serving 200 here keeps the access log
    # clean and stops Chrome from caching a 404.
    _BLANK_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    @app.get("/favicon.ico")
    def favicon():
        from fastapi.responses import Response
        fav = FRONTEND_DIR / "favicon.ico"
        if fav.exists():
            return FileResponse(str(fav))
        return Response(content=_BLANK_PNG, media_type="image/png")

    # Mount static files for css/js/lib under their own prefix.
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    app.mount("/lib", StaticFiles(directory=str(FRONTEND_DIR / "lib")), name="lib")
