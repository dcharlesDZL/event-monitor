"""Gold monitor: 金价(MA30/MA60) + 美元指数 DXY + 美债10年收益率 + COMEX 持仓.

数据源（免费公开接口）：
- 价格序列: Yahoo Finance 日线 (GC=F / DX-Y.NYB / ^TNX)
- COMEX 投机持仓: CFTC 官方 COT 报告 (publicreporting.cftc.gov, Socrata,
  每周五发布周二数据)，取非商业(投机)多空持仓算净多头。
- 美联储新闻走 news collector 的 category="fed"，不在本模块。

结果缓存在内存。观察结论仅供参考，不构成投资建议。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests

from config import (
    CFTC_GOLD_CODE,
    DXY_YAHOO_SYMBOL,
    GOLD_YAHOO_SYMBOL,
    US10Y_YAHOO_SYMBOL,
)

_UA = {"User-Agent": "Mozilla/5.0 (event-monitor)"}


def _ma(closes: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= n:
            s -= closes[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _yahoo_daily(symbol: str, rng: str = "1y") -> List[Dict]:
    """Daily close series: [{date, value}]."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={rng}&interval=1d"
    )
    j = requests.get(url, headers=_UA, timeout=15).json()
    res = j["chart"]["result"][0]
    from datetime import datetime, timezone
    out = []
    for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c is None:
            continue
        out.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "value": round(float(c), 4),
        })
    return out


def _chg(series: List[Dict], days: int) -> Optional[float]:
    if len(series) <= days:
        return None
    prev = series[-1 - days]["value"]
    if not prev:
        return None
    return round((series[-1]["value"] / prev - 1) * 100, 2)


def fetch_gold() -> Optional[Dict]:
    try:
        series = _yahoo_daily(GOLD_YAHOO_SYMBOL)
    except Exception as e:  # noqa: BLE001
        print(f"[gold] yahoo gold error: {e}")
        return None
    if len(series) < 65:
        return None
    closes = [p["value"] for p in series]
    ma30_s, ma60_s = _ma(closes, 30), _ma(closes, 60)
    tail = series[-120:]
    off = len(series) - len(tail)
    return {
        "price": closes[-1], "asof": series[-1]["date"],
        "chg": _chg(series, 1), "chg5": _chg(series, 5), "chg20": _chg(series, 20),
        "ma30": round(ma30_s[-1], 2), "ma60": round(ma60_s[-1], 2),
        "series": {
            "dates": [p["date"] for p in tail],
            "close": [p["value"] for p in tail],
            "ma30": [round(v, 2) if v else None for v in ma30_s[off:]],
            "ma60": [round(v, 2) if v else None for v in ma60_s[off:]],
        },
    }


def _fetch_simple(symbol: str, label: str) -> Optional[Dict]:
    try:
        series = _yahoo_daily(symbol, rng="6mo")
    except Exception as e:  # noqa: BLE001
        print(f"[gold] yahoo {label} error: {e}")
        return None
    if len(series) < 10:
        return None
    return {
        "price": series[-1]["value"], "asof": series[-1]["date"],
        "chg": _chg(series, 1), "chg5": _chg(series, 5), "chg20": _chg(series, 20),
        "series": series[-120:],
    }


# ---------------------------------------------------------------------------
# CFTC COT: COMEX 黄金非商业(投机)持仓，每周数据
# ---------------------------------------------------------------------------
def fetch_cot() -> Optional[Dict]:
    url = (
        "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
        f"?cftc_contract_market_code={CFTC_GOLD_CODE}"
        "&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=52"
    )
    try:
        rows = requests.get(url, headers=_UA, timeout=20).json()
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"unexpected response: {rows}")
    except Exception as e:  # noqa: BLE001
        print(f"[gold] CFTC COT error: {e}")
        return None

    series = []
    for r in reversed(rows):  # oldest -> newest
        try:
            long_ = float(r["noncomm_positions_long_all"])
            short = float(r["noncomm_positions_short_all"])
            series.append({
                "date": r["report_date_as_yyyy_mm_dd"][:10],
                "value": long_ - short,
                "long": long_, "short": short,
                "oi": float(r.get("open_interest_all") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not series:
        return None

    last = series[-1]
    prev = series[-2] if len(series) > 1 else None
    nets = [p["value"] for p in series]
    return {
        "net": last["value"],
        "net_chg": (last["value"] - prev["value"]) if prev else None,
        "long": last["long"], "short": last["short"],
        "open_interest": last["oi"],
        "net_52w_high": max(nets), "net_52w_low": min(nets),
        "asof": last["date"],
        "series": [{"date": p["date"], "value": p["value"]} for p in series],
    }


# ---------------------------------------------------------------------------
# 综合观察
# ---------------------------------------------------------------------------
def _observations(gold: Optional[Dict], dxy: Optional[Dict],
                  us10y: Optional[Dict], cot: Optional[Dict]) -> List[str]:
    obs: List[str] = []
    if gold:
        p, ma30, ma60 = gold["price"], gold["ma30"], gold["ma60"]
        if p > ma30 > ma60:
            obs.append(f"金价站上 MA30/MA60，日线多头排列 (MA30 {ma30:,.0f} > MA60 {ma60:,.0f})")
        elif p < ma30 < ma60:
            obs.append(f"金价跌破 MA30/MA60，日线空头排列 (MA30 {ma30:,.0f} < MA60 {ma60:,.0f})")
        elif p > ma30:
            obs.append("金价在 MA30 上方，短期趋势偏多")
        else:
            obs.append(f"金价跌破 MA30 ({ma30:,.0f})，短期趋势转弱")
    if dxy and dxy.get("chg5") is not None:
        if dxy["chg5"] >= 1:
            obs.append(f"美元指数 5 日 +{dxy['chg5']}%，美元走强对黄金构成压力")
        elif dxy["chg5"] <= -1:
            obs.append(f"美元指数 5 日 {dxy['chg5']}%，美元走弱利多黄金")
    if us10y and us10y.get("chg5") is not None:
        if us10y["chg5"] >= 3:
            obs.append(f"美债10年收益率 5 日 +{us10y['chg5']}%，实际利率上行利空黄金")
        elif us10y["chg5"] <= -3:
            obs.append(f"美债10年收益率 5 日 {us10y['chg5']}%，利率回落利多黄金")
    if cot:
        net, chg = cot["net"], cot.get("net_chg")
        if chg is not None:
            direction = "加多" if chg > 0 else "减多"
            obs.append(
                f"COMEX 投机净多头 {net:,.0f} 手 (周变化 {chg:+,.0f}，资金{direction})"
            )
        span = cot["net_52w_high"] - cot["net_52w_low"]
        if span > 0:
            pos = (net - cot["net_52w_low"]) / span
            if pos >= 0.85:
                obs.append("投机净多头接近 52 周高位，多头拥挤，注意回调风险")
            elif pos <= 0.15:
                obs.append("投机净多头接近 52 周低位，看空情绪极端，存在反弹空间")
    return obs


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
CACHE: Dict[str, object] = {
    "gold": None, "dxy": None, "us10y": None, "cot": None,
    "observations": [], "updated": 0,
}


def refresh_all() -> None:
    gold = fetch_gold()
    dxy = _fetch_simple(DXY_YAHOO_SYMBOL, "DXY")
    us10y = _fetch_simple(US10Y_YAHOO_SYMBOL, "US10Y")
    cot = fetch_cot()
    if gold:
        CACHE["gold"] = gold
    if dxy:
        CACHE["dxy"] = dxy
    if us10y:
        CACHE["us10y"] = us10y
    if cot:
        CACHE["cot"] = cot
    CACHE["observations"] = _observations(
        CACHE["gold"], CACHE["dxy"], CACHE["us10y"], CACHE["cot"]  # type: ignore[arg-type]
    )
    CACHE["updated"] = int(time.time())
