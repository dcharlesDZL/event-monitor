"""Sector sentiment for A股 / 美股.

小红书/抖音没有免费公开 API，所以用可免费获取的情绪代理指标：
- A股行业板块（东方财富）：涨跌幅、换手率、涨跌家数、主力资金净流入。
  高涨幅 + 高换手 + 全员上涨 = 情绪高涨（过热 -> 提示卖出）；
  大跌 + 放量 + 资金出逃 = 恐慌割肉（-> 提示买入）。
- 美股：CNN Fear & Greed 指数（整体），行业 ETF 的 RSI/动量/量能（分板块）。

情绪分 0-100，50 为中性。结果缓存在内存。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from config import (
    SENTIMENT_BUY_SCORE,
    SENTIMENT_SELL_SCORE,
    US_SECTOR_ETFS,
)

_UA = {"User-Agent": "Mozilla/5.0 (event-monitor)"}
_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}


def _num(v) -> Optional[float]:
    """East Money returns '-' for missing values."""
    if v is None or v == "-":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _signal(score: float) -> str:
    if score >= SENTIMENT_SELL_SCORE:
        return "sell"
    if score <= SENTIMENT_BUY_SCORE:
        return "buy"
    return "hold"


# ---------------------------------------------------------------------------
# A股行业板块 (East Money push2, free JSON)
# ---------------------------------------------------------------------------
def fetch_cn_sectors() -> List[Dict]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:90+t:2+f:!50"
        "&fields=f2,f3,f8,f12,f14,f62,f104,f105,f109,f160,f164,f165,f184"
    )
    try:
        j = requests.get(url, headers=_UA, timeout=15).json()
        rows = (j.get("data") or {}).get("diff") or []
    except Exception as e:  # noqa: BLE001
        print(f"[sentiment] eastmoney sectors error: {e}")
        return []

    out: List[Dict] = []
    for r in rows:
        chg = _num(r.get("f3"))          # 今日涨跌幅 %
        chg5 = _num(r.get("f109"))       # 5日涨跌幅 %
        chg10 = _num(r.get("f160"))      # 10日涨跌幅 %
        turnover = _num(r.get("f8"))     # 换手率 %
        up = _num(r.get("f104")) or 0    # 上涨家数
        down = _num(r.get("f105")) or 0  # 下跌家数
        flow_pct = _num(r.get("f184"))   # 今日主力净流入占比 %
        flow5_pct = _num(r.get("f165"))  # 5日主力净流入占比 %
        if chg is None:
            continue

        # raw 情绪值，0 为中性，正=亢奋，负=恐慌
        raw = _clamp(chg * 2, -10, 10)
        if chg5 is not None:
            raw += _clamp(chg5 * 1.2, -12, 12)
        if chg10 is not None:
            raw += _clamp(chg10 * 0.4, -5, 5)
        if up + down > 0:
            raw += (up - down) / (up + down) * 8  # 涨跌家数广度
        if turnover is not None:
            # 换手率是“热度”，方向跟随近期涨跌：放量上涨=亢奋，放量下跌=割肉
            direction = chg5 if (chg5 is not None and abs(chg5) > 0.5) else chg
            raw += min(turnover, 12) / 12 * 8 * (1 if direction >= 0 else -1)
        if flow_pct is not None:
            raw += _clamp(flow_pct * 0.5, -5, 5)
        if flow5_pct is not None:
            raw += _clamp(flow5_pct * 0.3, -4, 4)

        out.append({
            "code": r.get("f12"), "name": r.get("f14"),
            "raw": raw,
            "chg": chg, "chg5": chg5, "chg10": chg10,
            "turnover": turnover, "flow_pct": flow_pct,
            "up": int(up), "down": int(down),
        })

    # 最终情绪分 = 绝对情绪(60%) + 横截面排名(40%)。
    # 排名部分避免普涨/普跌日全市场同向饱和，只让相对最亢奋/最恐慌的板块触发信号。
    out.sort(key=lambda x: x["raw"])
    n = len(out)
    for i, s in enumerate(out):
        abs_part = 50 + _clamp(s["raw"] * 0.7, -50, 50)
        rank_part = (i + 0.5) / n * 100 if n else 50
        score = round(_clamp(0.6 * abs_part + 0.4 * rank_part, 0, 100), 1)
        s["score"] = score
        s["signal"] = _signal(score)
        del s["raw"]
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# 美股行业 ETF (Yahoo Finance) — RSI / 动量 / 量能
# ---------------------------------------------------------------------------
def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 1)


def fetch_us_sectors() -> List[Dict]:
    out: List[Dict] = []
    for etf in US_SECTOR_ETFS:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{etf['symbol']}"
            "?range=3mo&interval=1d"
        )
        try:
            j = requests.get(url, headers=_UA, timeout=15).json()
            res = j["chart"]["result"][0]
            quote = res["indicators"]["quote"][0]
            closes = [c for c in quote["close"] if c is not None]
            vols = [v for v in quote["volume"] if v]
            if len(closes) < 25:
                raise ValueError("not enough data")
        except Exception as e:  # noqa: BLE001
            print(f"[sentiment] yahoo {etf['symbol']} error: {e}")
            continue

        last = closes[-1]
        chg5 = (last / closes[-6] - 1) * 100 if len(closes) > 6 else 0.0
        chg20 = (last / closes[-21] - 1) * 100 if len(closes) > 21 else 0.0
        rsi = _rsi(closes)
        vol_ratio = None
        if len(vols) > 21:
            avg20 = sum(vols[-21:-1]) / 20
            if avg20:
                vol_ratio = vols[-1] / avg20

        score = 50.0
        score += _clamp(chg5 * 1.5, -15, 15)
        score += _clamp(chg20 * 0.5, -10, 10)
        if rsi is not None:
            score += _clamp((rsi - 50) * 0.6, -18, 18)
        if vol_ratio is not None:
            score += _clamp((vol_ratio - 1) * 10, -10, 10) * (1 if chg5 >= 0 else -1)
        score = round(_clamp(score, 0, 100), 1)

        out.append({
            "symbol": etf["symbol"], "name": etf["name"],
            "score": score, "signal": _signal(score),
            "price": round(last, 2),
            "chg5": round(chg5, 2), "chg20": round(chg20, 2),
            "rsi": rsi,
            "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# CNN Fear & Greed (美股整体情绪, best-effort)
# ---------------------------------------------------------------------------
_FNG_RATING_ZH = {
    "extreme fear": "极度恐惧", "fear": "恐惧", "neutral": "中性",
    "greed": "贪婪", "extreme greed": "极度贪婪",
}


def fetch_us_fear_greed() -> Optional[Dict]:
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        j = requests.get(url, headers=_BROWSER_UA, timeout=15).json()
        fg = j.get("fear_and_greed") or {}
        score = fg.get("score")
        if score is None:
            return None
        rating = (fg.get("rating") or "").lower()
        return {
            "score": round(float(score), 1),
            "rating": rating,
            "rating_zh": _FNG_RATING_ZH.get(rating, rating),
            "asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[sentiment] CNN fear&greed error: {e}")
        return None


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
CACHE: Dict[str, object] = {
    "cn_sectors": [], "us_sectors": [], "us_fear_greed": None, "updated": 0,
}


def refresh_all() -> None:
    CACHE["cn_sectors"] = fetch_cn_sectors()
    CACHE["us_sectors"] = fetch_us_sectors()
    CACHE["us_fear_greed"] = fetch_us_fear_greed()
    CACHE["updated"] = int(time.time())
