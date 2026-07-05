"""Collect market series (Stooq), macro indicators (World Bank), and search
index (Google Trends, best-effort). Results are cached in memory."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List

import requests

from config import (
    MARKET_RANGE,
    MARKET_SERIES,
    TRENDS_GEO,
    TRENDS_KEYWORDS,
    WORLDBANK_COUNTRIES,
    WORLDBANK_COUNTRY_NAMES,
    WORLDBANK_INDICATORS,
)

_UA = {"User-Agent": "Mozilla/5.0 (event-monitor)"}


def _pct(series: List[Dict]) -> float:
    """Percent change of last point vs previous."""
    if len(series) < 2:
        return 0.0
    prev, last = series[-2]["value"], series[-1]["value"]
    if not prev:
        return 0.0
    return round((last - prev) / prev * 100, 2)


# ---------------------------------------------------------------------------
# Yahoo Finance daily chart
# ---------------------------------------------------------------------------
def fetch_market() -> List[Dict]:
    out: List[Dict] = []
    for s in MARKET_SERIES:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{s['symbol']}"
            f"?range={MARKET_RANGE}&interval=1d"
        )
        try:
            j = requests.get(url, headers=_UA, timeout=15).json()
            res = j["chart"]["result"][0]
            stamps = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            series = []
            for ts, c in zip(stamps, closes):
                if c is None:
                    continue
                date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                series.append({"date": date, "value": round(float(c), 4)})
            if not series:
                raise ValueError("empty series")
            out.append({
                "symbol": s["symbol"], "name": s["name"], "group": s["group"],
                "latest": series[-1]["value"], "change_pct": _pct(series),
                "asof": series[-1]["date"], "series": series,
            })
        except Exception as e:  # noqa: BLE001
            print(f"[metrics] yahoo {s['symbol']} error: {e}")
    return out


# ---------------------------------------------------------------------------
# World Bank macro indicators (annual)
# ---------------------------------------------------------------------------
def fetch_worldbank() -> List[Dict]:
    out: List[Dict] = []
    countries = ";".join(WORLDBANK_COUNTRIES)
    for ind in WORLDBANK_INDICATORS:
        url = (
            f"https://api.worldbank.org/v2/country/{countries}/indicator/{ind['code']}"
            "?format=json&per_page=500&date=2014:2025"
        )
        try:
            data = requests.get(url, headers=_UA, timeout=20).json()
            rows = data[1] if isinstance(data, list) and len(data) > 1 else []
        except Exception as e:  # noqa: BLE001
            print(f"[metrics] worldbank {ind['code']} error: {e}")
            continue
        by_country: Dict[str, List[Dict]] = {}
        for r in rows:
            if r.get("value") is None:
                continue
            iso = r["countryiso3code"]
            by_country.setdefault(iso, []).append(
                {"date": r["date"], "value": float(r["value"])}
            )
        for iso, series in by_country.items():
            series.sort(key=lambda x: x["date"])
            out.append({
                "indicator": ind["name"], "code": ind["code"],
                "country": WORLDBANK_COUNTRY_NAMES.get(iso, iso), "iso": iso,
                "latest": series[-1]["value"], "asof": series[-1]["date"],
                "series": series,
            })
    return out


# ---------------------------------------------------------------------------
# Google Trends (best-effort; pytrends optional)
# ---------------------------------------------------------------------------
def fetch_trends() -> List[Dict]:
    out: List[Dict] = []
    try:
        from pytrends.request import TrendReq
    except Exception:  # noqa: BLE001
        print("[metrics] pytrends not installed; skipping trends")
        return out
    try:
        py = TrendReq(hl="en-US", tz=0)
        py.build_payload(TRENDS_KEYWORDS, timeframe="today 3-m", geo=TRENDS_GEO)
        df = py.interest_over_time()
    except Exception as e:  # noqa: BLE001
        print(f"[metrics] trends error: {e}")
        return out
    if df is None or df.empty:
        return out
    dates = [d.strftime("%Y-%m-%d") for d in df.index]
    for kw in TRENDS_KEYWORDS:
        if kw not in df:
            continue
        series = [{"date": d, "value": int(v)} for d, v in zip(dates, df[kw].tolist())]
        out.append({
            "keyword": kw, "latest": series[-1]["value"],
            "change_pct": _pct(series), "asof": series[-1]["date"], "series": series,
        })
    return out


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
CACHE: Dict[str, object] = {
    "market": [], "worldbank": [], "trends": [],
    "updated": {"market": 0, "worldbank": 0, "trends": 0},
}


def refresh_market() -> None:
    CACHE["market"] = fetch_market()
    CACHE["updated"]["market"] = int(time.time())  # type: ignore[index]


def refresh_worldbank() -> None:
    CACHE["worldbank"] = fetch_worldbank()
    CACHE["updated"]["worldbank"] = int(time.time())  # type: ignore[index]


def refresh_trends() -> None:
    CACHE["trends"] = fetch_trends()
    CACHE["updated"]["trends"] = int(time.time())  # type: ignore[index]
