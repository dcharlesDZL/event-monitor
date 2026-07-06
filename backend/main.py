"""FastAPI app: serves the JSON API and the static frontend."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import config
import db
import scheduler
from collectors import crypto, metrics, sentiment

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = FastAPI(title="Event Monitor")


# ---------------------------------------------------------------------------
# Rate limiting (slowapi).
#
# This is a *backstop*. The authoritative per-IP limit should live in the
# reverse proxy (see the deploy nginx.conf). The client IP is taken from the
# headers that proxy sets — keep uvicorn bound to 127.0.0.1 and never expose
# it directly, or these headers become spoofable.
#
# NOTE: default storage is in-memory and per-process. If you run uvicorn with
# >1 worker and need a hard shared ceiling, point slowapi at Redis via
# `storage_uri=...`; otherwise let the proxy enforce the real limit.
# ---------------------------------------------------------------------------
def _client_ip(request: Request) -> str:
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Cache-Control for the read-only API. Data is refreshed on a schedule (see
# config.*_REFRESH_SEC), so short edge/CDN caching absorbs most L7 traffic
# without serving meaningfully stale data. /api/health stays uncached so it
# remains a real liveness probe.
# ---------------------------------------------------------------------------
_API_CACHE = {
    "/api/metrics":   "public, max-age=60, s-maxage=300",
    "/api/sentiment": "public, max-age=60, s-maxage=300",
    "/api/crypto":    "public, max-age=30, s-maxage=120",
    "/api/news":      "public, max-age=30, s-maxage=120",
}


@app.middleware("http")
async def _cache_control(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200:
        cc = _API_CACHE.get(request.url.path)
        if cc:
            response.headers["Cache-Control"] = cc
    return response


def _require_api_enabled() -> None:
    """Guard: block /api/* routes when the API switch is off."""
    if not config.API_ENABLED:
        raise HTTPException(status_code=404, detail="API is disabled")


api = APIRouter(dependencies=[Depends(_require_api_enabled)])


@app.on_event("startup")
def _startup() -> None:
    scheduler.start()


@api.get("/api/metrics")
@limiter.limit("120/minute")
def api_metrics(request: Request):
    return {
        "market": metrics.CACHE["market"],
        "worldbank": metrics.CACHE["worldbank"],
        "trends": metrics.CACHE["trends"],
        "updated": metrics.CACHE["updated"],
    }


@api.get("/api/sentiment")
@limiter.limit("120/minute")
def api_sentiment(request: Request):
    return {
        "cn_sectors": sentiment.CACHE["cn_sectors"],
        "us_sectors": sentiment.CACHE["us_sectors"],
        "us_fear_greed": sentiment.CACHE["us_fear_greed"],
        "updated": sentiment.CACHE["updated"],
    }


@api.get("/api/crypto")
@limiter.limit("120/minute")
def api_crypto(request: Request):
    return {
        "coins": crypto.CACHE["coins"],
        "fear_greed": crypto.CACHE["fear_greed"],
        "updated": crypto.CACHE["updated"],
    }


@api.get("/api/news")
@limiter.limit("60/minute")
def api_news(request: Request, category: str = "", country: str = "", limit: int = 100):
    return {"items": db.query_news(category, country, min(limit, 300))}


@api.get("/api/health")
@limiter.limit("120/minute")
def api_health(request: Request):
    return {
        "ok": True,
        "metrics_updated": metrics.CACHE["updated"],
        "news_count": len(db.query_news(limit=300)),
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.include_router(api)
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
