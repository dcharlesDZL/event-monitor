"""Background refresh loops. Each source runs on its own interval thread."""
from __future__ import annotations

import threading
import time
import traceback

import db
from collectors import crypto, gold, metrics, news, sentiment
from config import (
    CRYPTO_REFRESH_SEC,
    GOLD_REFRESH_SEC,
    METRICS_REFRESH_SEC,
    NEWS_REFRESH_SEC,
    SENTIMENT_REFRESH_SEC,
    TRENDS_REFRESH_SEC,
)


def _loop(name: str, fn, interval: int) -> None:
    while True:
        start = time.time()
        try:
            fn()
            print(f"[scheduler] {name} ok ({time.time()-start:.1f}s)")
        except Exception:  # noqa: BLE001
            print(f"[scheduler] {name} FAILED:\n{traceback.format_exc()}")
        time.sleep(interval)


def _refresh_news() -> None:
    items = news.collect_all()
    new = db.upsert_news(items)
    db.prune()
    print(f"[scheduler] news: {len(items)} fetched, {new} new")


def start() -> None:
    """Spawn daemon threads. Returns immediately."""
    db.init()
    jobs = [
        ("market", metrics.refresh_market, METRICS_REFRESH_SEC),
        ("worldbank", metrics.refresh_worldbank, METRICS_REFRESH_SEC),
        ("trends", metrics.refresh_trends, TRENDS_REFRESH_SEC),
        ("news", _refresh_news, NEWS_REFRESH_SEC),
        ("sentiment", sentiment.refresh_all, SENTIMENT_REFRESH_SEC),
        ("crypto", crypto.refresh_all, CRYPTO_REFRESH_SEC),
        ("gold", gold.refresh_all, GOLD_REFRESH_SEC),
    ]
    for name, fn, interval in jobs:
        t = threading.Thread(target=_loop, args=(name, fn, interval), daemon=True)
        t.start()
