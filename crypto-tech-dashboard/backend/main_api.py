"""FastAPI app for Vercel deployment — no APScheduler, no fetcher imports.

On Vercel, data is fetched by GitHub Actions and stored in Neon Postgres.
This module only wires the API routes and serves the static frontend.
The DataService reads from Postgres (DATABASE_URL env var) when running here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

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
from backend.services.data_service import DataService, set_service

log = logging.getLogger("backend.main_api")

# frontend/ is one level above this file's directory (backend/).
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class _DbReloadFetcher:
    """Lightweight stub fetcher for Vercel.

    The real Fetcher (CCXT + CoinGecko) is not imported on Vercel to keep
    the bundle small. When the user clicks Refresh, this stub reloads the
    in-memory cache from Neon Postgres (fast, ~1-2 s) instead of re-fetching
    from exchanges (which would timeout the serverless function).
    """

    _progress = {
        "phase": "idle", "current": 0, "total": 0,
        "last_token": None, "started_at": None, "finished_at": None,
    }

    def run_daily_update(self):
        from backend.services.data_service import get_service
        svc = get_service()
        svc.refresh_from_disk()
        log.info("Vercel cache reloaded from Postgres")

    def run_stocks_daily_update(self):
        pass  # included in run_daily_update cache reload above

    def run_full_initial_load(self):
        self.run_daily_update()


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = DataService()
    svc.refresh_from_disk()   # reads from Postgres when DATABASE_URL is set
    set_service(svc)
    log.info(
        "DataService initialised — %d tokens loaded (db_mode=%s)",
        len(svc.top_df) if svc.top_df is not None else 0,
        bool(__import__("os").environ.get("DATABASE_URL")),
    )
    # Bind the lightweight stub so /api/system/refresh works on Vercel.
    routes_system.bind_fetcher(_DbReloadFetcher())
    yield


app = FastAPI(title="IOSG Crypto Tech Dashboard", lifespan=lifespan)


# Vercel override: must be registered BEFORE routes_system.router so FastAPI
# matches this handler first (first-match wins).
# Problem: the frontend polls finished_at from /api/system/status waiting for
# it to change, but on Vercel that field only updates when GitHub Actions runs.
# Returning {"status":"skipped"} switches the frontend to the fast path: it
# checks phase=="idle" from /api/system/refresh-progress (always idle here),
# resolves in ~2 s instead of timing out after 10 min.
@app.post("/api/system/refresh")
async def vercel_system_refresh(full: bool = False):
    from backend.services.data_service import get_service
    get_service().refresh_from_disk()
    return {"status": "skipped"}


# --- API routes ---
app.include_router(routes_tokens.router)
app.include_router(routes_indicators.router)
app.include_router(routes_scores.router)
app.include_router(routes_backtest.router)
app.include_router(routes_system.router)
app.include_router(routes_admin.router)
app.include_router(routes_market.router)
app.include_router(routes_robustness.router)
app.include_router(routes_scoring_meta.router)


@app.get("/health")
def health():
    return {"ok": True}


# --- Static frontend ---
if _FRONTEND_DIR.exists():
    @app.get("/")
    def index():
        idx = _FRONTEND_DIR / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return JSONResponse({"error": "frontend index.html missing"}, status_code=404)

    @app.get("/login.html")
    def login_page():
        page = _FRONTEND_DIR / "login.html"
        if page.exists():
            return FileResponse(str(page))
        return JSONResponse({"error": "login.html missing"}, status_code=404)

    _BLANK_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    @app.get("/favicon.ico")
    def favicon():
        from fastapi.responses import Response
        fav = _FRONTEND_DIR / "favicon.ico"
        if fav.exists():
            return FileResponse(str(fav))
        return Response(content=_BLANK_PNG, media_type="image/png")

    app.mount("/css", StaticFiles(directory=str(_FRONTEND_DIR / "css")), name="css")
    app.mount("/js",  StaticFiles(directory=str(_FRONTEND_DIR / "js")),  name="js")
    app.mount("/lib", StaticFiles(directory=str(_FRONTEND_DIR / "lib")), name="lib")
