"""FastAPI app: serves the JSON API and the static frontend."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db
import scheduler
from collectors import crypto, metrics, sentiment

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = FastAPI(title="Event Monitor")


@app.on_event("startup")
def _startup() -> None:
    scheduler.start()


@app.get("/api/metrics")
def api_metrics():
    return {
        "market": metrics.CACHE["market"],
        "worldbank": metrics.CACHE["worldbank"],
        "trends": metrics.CACHE["trends"],
        "updated": metrics.CACHE["updated"],
    }


@app.get("/api/sentiment")
def api_sentiment():
    return {
        "cn_sectors": sentiment.CACHE["cn_sectors"],
        "us_sectors": sentiment.CACHE["us_sectors"],
        "us_fear_greed": sentiment.CACHE["us_fear_greed"],
        "updated": sentiment.CACHE["updated"],
    }


@app.get("/api/crypto")
def api_crypto():
    return {
        "coins": crypto.CACHE["coins"],
        "fear_greed": crypto.CACHE["fear_greed"],
        "updated": crypto.CACHE["updated"],
    }


@app.get("/api/news")
def api_news(category: str = "", country: str = "", limit: int = 100):
    return {"items": db.query_news(category, country, min(limit, 300))}


@app.get("/api/health")
def api_health():
    return {
        "ok": True,
        "metrics_updated": metrics.CACHE["updated"],
        "news_count": len(db.query_news(limit=300)),
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
