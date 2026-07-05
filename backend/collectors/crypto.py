"""Crypto trading signals for BTC / ETH / SOL.

数据源（全部免费公开接口）：
- 现货日K: Binance /api/v3/klines，失败回退 OKX /api/v5/market/candles
- 永续: 资金费率、持仓量(7日变化)、多空账户比 (Binance fapi, OKX 回退)
- 期权: Deribit Put/Call 持仓比
- 整体情绪: alternative.me Crypto Fear & Greed

技术面: MA30/MA60、RSI14、MACD(12,26,9)、摆动点聚类得到的支撑/压力位。
综合打分 -> 做多 / 做空 / 观望 建议 + 理由列表。仅供参考，不构成投资建议。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

from config import CRYPTO_SYMBOLS

_UA = {"User-Agent": "Mozilla/5.0 (event-monitor)"}


def _get_json(url: str, timeout: int = 15):
    return requests.get(url, headers=_UA, timeout=timeout).json()


# ---------------------------------------------------------------------------
# K线 (Binance -> OKX fallback)。返回 [{date, open, high, low, close, volume}]
# ---------------------------------------------------------------------------
def _binance_klines(symbol: str, limit: int = 200) -> List[Dict]:
    j = _get_json(
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
    )
    if not isinstance(j, list):
        raise ValueError(f"binance klines: {j}")
    out = []
    for k in j:
        out.append({
            "date": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        })
    return out


def _okx_klines(inst: str, limit: int = 200) -> List[Dict]:
    j = _get_json(
        f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar=1Dutc&limit={limit}"
    )
    rows = j.get("data") or []
    if not rows:
        raise ValueError(f"okx klines: {j.get('msg')}")
    out = []
    for k in reversed(rows):  # OKX returns newest first
        out.append({
            "date": datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        })
    return out


def fetch_klines(cfg: Dict) -> List[Dict]:
    try:
        return _binance_klines(cfg["binance"])
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] binance klines {cfg['symbol']} failed ({e}), trying OKX")
        return _okx_klines(cfg["okx"])


# ---------------------------------------------------------------------------
# 技术指标
# ---------------------------------------------------------------------------
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
    return round(100 - 100 / (1 + avg_g / avg_l), 1)


def _ema(vals: List[float], n: int) -> List[float]:
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _macd_hist(closes: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """Returns (last_hist, prev_hist)."""
    if len(closes) < 35:
        return None, None
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]
    return hist[-1], hist[-2]


def _cluster(levels: List[float], tol: float = 0.012) -> List[Tuple[float, int]]:
    """Merge nearby price levels; returns [(price, touches)] sorted by price."""
    if not levels:
        return []
    levels = sorted(levels)
    clusters: List[List[float]] = [[levels[0]]]
    for v in levels[1:]:
        if v <= clusters[-1][-1] * (1 + tol):
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [(sum(c) / len(c), len(c)) for c in clusters]


def _support_resistance(klines: List[Dict], price: float, window: int = 4,
                        lookback: int = 120) -> Tuple[Optional[float], Optional[float]]:
    """Swing-point clustering: nearest support below / resistance above price."""
    ks = klines[-lookback:]
    highs = [k["high"] for k in ks]
    lows = [k["low"] for k in ks]
    piv_hi, piv_lo = [], []
    for i in range(window, len(ks) - window):
        seg_h = highs[i - window: i + window + 1]
        seg_l = lows[i - window: i + window + 1]
        if highs[i] == max(seg_h):
            piv_hi.append(highs[i])
        if lows[i] == min(seg_l):
            piv_lo.append(lows[i])
    res_levels = [p for p, _ in _cluster(piv_hi) if p > price * 1.005]
    sup_levels = [p for p, _ in _cluster(piv_lo) if p < price * 0.995]
    resistance = min(res_levels) if res_levels else (max(highs) if max(highs) > price else None)
    support = max(sup_levels) if sup_levels else (min(lows) if min(lows) < price else None)
    return support, resistance


# ---------------------------------------------------------------------------
# 永续合约 (Binance fapi -> OKX fallback)
# ---------------------------------------------------------------------------
def fetch_perp(cfg: Dict) -> Dict:
    out: Dict = {"funding": None, "oi_chg7d": None, "long_short": None}
    sym, okx_swap = cfg["binance"], cfg["okx"] + "-SWAP"

    try:  # funding rate (per 8h)
        j = _get_json(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}")
        out["funding"] = float(j["lastFundingRate"])
    except Exception:  # noqa: BLE001
        try:
            j = _get_json(f"https://www.okx.com/api/v5/public/funding-rate?instId={okx_swap}")
            out["funding"] = float(j["data"][0]["fundingRate"])
        except Exception as e:  # noqa: BLE001
            print(f"[crypto] funding {cfg['symbol']} error: {e}")

    try:  # open interest 7d change (%)
        j = _get_json(
            f"https://fapi.binance.com/futures/data/openInterestHist"
            f"?symbol={sym}&period=1d&limit=8"
        )
        if isinstance(j, list) and len(j) >= 2:
            first = float(j[0]["sumOpenInterestValue"])
            last = float(j[-1]["sumOpenInterestValue"])
            if first:
                out["oi_chg7d"] = round((last / first - 1) * 100, 1)
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] OI {cfg['symbol']} error: {e}")

    try:  # global long/short account ratio
        j = _get_json(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            f"?symbol={sym}&period=1d&limit=1"
        )
        if isinstance(j, list) and j:
            out["long_short"] = round(float(j[-1]["longShortRatio"]), 2)
    except Exception:  # noqa: BLE001
        try:
            ccy = cfg["symbol"]
            j = _get_json(
                "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
                f"?ccy={ccy}&period=1D"
            )
            if j.get("data"):
                out["long_short"] = round(float(j["data"][0][1]), 2)
        except Exception as e:  # noqa: BLE001
            print(f"[crypto] long/short {cfg['symbol']} error: {e}")
    return out


# ---------------------------------------------------------------------------
# 期权 (Deribit): Put/Call 持仓比
# ---------------------------------------------------------------------------
def fetch_options_pcr(currency: str) -> Optional[float]:
    try:
        j = _get_json(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
            f"?currency={currency}&kind=option",
            timeout=20,
        )
        call_oi, put_oi = 0.0, 0.0
        for it in j.get("result") or []:
            oi = it.get("open_interest") or 0
            name = it.get("instrument_name", "")
            if name.endswith("-C"):
                call_oi += oi
            elif name.endswith("-P"):
                put_oi += oi
        if call_oi <= 0:
            return None
        return round(put_oi / call_oi, 2)
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] deribit {currency} error: {e}")
        return None


# ---------------------------------------------------------------------------
# Crypto Fear & Greed (alternative.me)
# ---------------------------------------------------------------------------
_FNG_ZH = {
    "Extreme Fear": "极度恐惧", "Fear": "恐惧", "Neutral": "中性",
    "Greed": "贪婪", "Extreme Greed": "极度贪婪",
}


def fetch_fear_greed() -> Optional[Dict]:
    try:
        j = _get_json("https://api.alternative.me/fng/?limit=1")
        d = (j.get("data") or [{}])[0]
        label = d.get("value_classification", "")
        return {
            "value": int(d["value"]),
            "label": label,
            "label_zh": _FNG_ZH.get(label, label),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] fear&greed error: {e}")
        return None


# ---------------------------------------------------------------------------
# 综合打分 -> 建议
# ---------------------------------------------------------------------------
def _analyze(cfg: Dict) -> Optional[Dict]:
    try:
        klines = fetch_klines(cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] klines {cfg['symbol']} error: {e}")
        return None
    if len(klines) < 65:
        return None

    closes = [k["close"] for k in klines]
    price = closes[-1]
    chg24h = round((price / closes[-2] - 1) * 100, 2) if closes[-2] else 0.0
    ma30_series = _ma(closes, 30)
    ma60_series = _ma(closes, 60)
    ma30, ma60 = ma30_series[-1], ma60_series[-1]
    rsi = _rsi(closes)
    hist, prev_hist = _macd_hist(closes)
    support, resistance = _support_resistance(klines, price)
    perp = fetch_perp(cfg)
    pcr = fetch_options_pcr(cfg["deribit"])

    score = 0.0
    reasons: List[str] = []

    # --- 趋势 (MA30/MA60) ---
    if ma30 and ma60:
        if price > ma30 > ma60:
            score += 2
            reasons.append(f"价格站上 MA30/MA60，多头排列 (MA30 {ma30:,.0f} > MA60 {ma60:,.0f})")
        elif price < ma30 < ma60:
            score -= 2
            reasons.append(f"价格跌破 MA30/MA60，空头排列 (MA30 {ma30:,.0f} < MA60 {ma60:,.0f})")
        elif price > ma30:
            score += 1
            reasons.append("价格站上 MA30，短期趋势偏多")
        else:
            score -= 1
            reasons.append("价格跌破 MA30，短期趋势偏空")

    # --- RSI ---
    if rsi is not None:
        if rsi >= 70:
            score -= 1.5
            reasons.append(f"RSI14 = {rsi} 超买，追多风险大")
        elif rsi <= 30:
            score += 1.5
            reasons.append(f"RSI14 = {rsi} 超卖，存在反弹机会")

    # --- MACD ---
    if hist is not None and prev_hist is not None:
        if hist > 0 and hist > prev_hist:
            score += 1
            reasons.append("MACD 红柱放大，动能向上")
        elif hist < 0 and hist < prev_hist:
            score -= 1
            reasons.append("MACD 绿柱放大，动能向下")

    # --- 永续: 资金费率 (拥挤度，反向指标) ---
    funding = perp["funding"]
    if funding is not None:
        if funding >= 0.0005:
            score -= 1.5
            reasons.append(f"资金费率 {funding*100:.3f}%/8h 偏高，多头拥挤，谨防多杀多")
        elif funding <= -0.0001:
            score += 1.5
            reasons.append(f"资金费率 {funding*100:.3f}%/8h 为负，空头拥挤，有逼空可能")

    # --- 永续: 持仓量与价格配合 ---
    oi_chg = perp["oi_chg7d"]
    if oi_chg is not None and len(closes) > 8:
        px_chg7 = (price / closes[-8] - 1) * 100
        if oi_chg > 3 and px_chg7 > 0:
            score += 1
            reasons.append(f"持仓量 7 日 +{oi_chg}%，增仓上行，趋势有资金支持")
        elif oi_chg > 3 and px_chg7 < 0:
            score -= 1
            reasons.append(f"持仓量 7 日 +{oi_chg}% 但价格下跌，空头主动增仓")

    # --- 永续: 多空账户比 (极端值反向) ---
    ls = perp["long_short"]
    if ls is not None:
        if ls >= 2.5:
            score -= 1
            reasons.append(f"多空账户比 {ls} 过高，散户多头扎堆（反向偏空）")
        elif ls <= 0.8:
            score += 1
            reasons.append(f"多空账户比 {ls} 过低，散户普遍看空（反向偏多）")

    # --- 期权: Put/Call 持仓比 (极端值反向) ---
    if pcr is not None:
        if pcr >= 1.1:
            score += 1
            reasons.append(f"期权 Put/Call 比 {pcr}，期权市场偏防御/恐慌（反向偏多）")
        elif pcr <= 0.5:
            score -= 1
            reasons.append(f"期权 Put/Call 比 {pcr}，期权市场过度乐观（反向偏空）")

    # --- 支撑/压力位置提示 ---
    if resistance and price >= resistance * 0.98:
        reasons.append(f"接近压力位 {resistance:,.0f}，突破前不宜追多")
    if support and price <= support * 1.02:
        reasons.append(f"贴近支撑位 {support:,.0f}，跌破则止损离场")

    if score >= 3:
        verdict, verdict_label = "long", "做多"
    elif score >= 1:
        verdict, verdict_label = "lean_long", "谨慎偏多"
    elif score <= -3:
        verdict, verdict_label = "short", "做空"
    elif score <= -1:
        verdict, verdict_label = "lean_short", "谨慎偏空"
    else:
        verdict, verdict_label = "neutral", "观望"

    tail = klines[-120:]
    offset = len(klines) - len(tail)
    series = {
        "dates": [k["date"] for k in tail],
        "close": [k["close"] for k in tail],
        "ma30": [round(v, 2) if v else None for v in ma30_series[offset:]],
        "ma60": [round(v, 2) if v else None for v in ma60_series[offset:]],
    }

    return {
        "symbol": cfg["symbol"], "name": cfg["name"],
        "price": price, "chg24h": chg24h,
        "ma30": round(ma30, 2) if ma30 else None,
        "ma60": round(ma60, 2) if ma60 else None,
        "rsi": rsi,
        "macd_hist": round(hist, 2) if hist is not None else None,
        "support": round(support, 2) if support else None,
        "resistance": round(resistance, 2) if resistance else None,
        "funding": funding,
        "oi_chg7d": oi_chg,
        "long_short": ls,
        "pcr": pcr,
        "score": round(score, 1),
        "verdict": verdict, "verdict_label": verdict_label,
        "reasons": reasons,
        "series": series,
    }


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
CACHE: Dict[str, object] = {"coins": [], "fear_greed": None, "updated": 0}


def refresh_all() -> None:
    coins = []
    for cfg in CRYPTO_SYMBOLS:
        r = _analyze(cfg)
        if r:
            coins.append(r)
    if coins:
        CACHE["coins"] = coins
    CACHE["fear_greed"] = fetch_fear_greed()
    CACHE["updated"] = int(time.time())
