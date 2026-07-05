"""Central configuration: data sources for metrics and news feeds.

Everything here uses free / public sources (no API key required), so the app
runs out of the box. You can edit the lists below to add/remove sources.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Refresh intervals (seconds)
# ---------------------------------------------------------------------------
METRICS_REFRESH_SEC = 60 * 30   # market/economic series: every 30 min
NEWS_REFRESH_SEC = 60 * 10      # news feeds: every 10 min
TRENDS_REFRESH_SEC = 60 * 60    # google trends: every hour (rate-limit prone)
SENTIMENT_REFRESH_SEC = 60 * 30  # sector sentiment: every 30 min
CRYPTO_REFRESH_SEC = 60 * 15     # crypto signals: every 15 min

# ---------------------------------------------------------------------------
# 1) Market & commodity series via Yahoo Finance (free JSON, no key)
#    https://query1.finance.yahoo.com/v8/finance/chart/<symbol>?range=6mo&interval=1d
# ---------------------------------------------------------------------------
MARKET_RANGE = "6mo"
MARKET_SERIES = [
    {"symbol": "^GSPC",      "name": "S&P 500",            "group": "美股"},
    {"symbol": "^IXIC",      "name": "Nasdaq",             "group": "美股"},
    {"symbol": "^DJI",       "name": "道琼斯",             "group": "美股"},
    {"symbol": "000001.SS",  "name": "上证综指",           "group": "亚太股市"},
    {"symbol": "^HSI",       "name": "恒生指数",           "group": "亚太股市"},
    {"symbol": "^N225",      "name": "日经225",            "group": "亚太股市"},
    {"symbol": "^KS11",      "name": "韩国KOSPI",          "group": "亚太股市"},
    {"symbol": "^GDAXI",     "name": "德国DAX",            "group": "欧洲股市"},
    {"symbol": "^TNX",       "name": "美债10年收益率",     "group": "利率/汇率"},
    {"symbol": "CNY=X",      "name": "美元/人民币",        "group": "利率/汇率"},
    {"symbol": "EURUSD=X",   "name": "欧元/美元",          "group": "利率/汇率"},
    {"symbol": "JPY=X",      "name": "美元/日元",          "group": "利率/汇率"},
    {"symbol": "GC=F",       "name": "黄金",               "group": "大宗商品"},
    {"symbol": "CL=F",       "name": "原油WTI",            "group": "大宗商品"},
    {"symbol": "BTC-USD",    "name": "比特币",             "group": "大宗商品"},
]

# ---------------------------------------------------------------------------
# 2) Macro indicators via World Bank API (free, no key)
#    Annual data for selected economies.
# ---------------------------------------------------------------------------
WORLDBANK_COUNTRIES = ["USA", "CHN", "JPN", "KOR", "EMU"]  # EMU = Euro area
WORLDBANK_COUNTRY_NAMES = {
    "USA": "美国", "CHN": "中国", "JPN": "日本", "KOR": "韩国", "EMU": "欧元区",
}
WORLDBANK_INDICATORS = [
    {"code": "NY.GDP.MKTP.KD.ZG", "name": "GDP增速(%)"},
    {"code": "FP.CPI.TOTL.ZG",    "name": "通胀CPI(%)"},
    {"code": "SL.UEM.TOTL.ZS",    "name": "失业率(%)"},
]

# ---------------------------------------------------------------------------
# 3) Google Trends keywords (search index). Best-effort; may be rate limited.
# ---------------------------------------------------------------------------
TRENDS_KEYWORDS = ["AI", "recession", "inflation", "Bitcoin", "ChatGPT"]
TRENDS_GEO = ""  # "" = worldwide, or "US", "CN" etc.

# ---------------------------------------------------------------------------
# 4) News & policy feeds.
#    category: policy | tech | breaking
#    country:  CN | US | JP | KR | EU | global
# ---------------------------------------------------------------------------

def _gnews(query: str, hl: str, gl: str, ceid: str) -> str:
    from urllib.parse import quote
    return (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + f"&hl={hl}&gl={gl}&ceid={ceid}"
    )


NEWS_FEEDS = [
    # ---- Policy: 各国政策发布 ----
    {"category": "policy", "country": "CN", "name": "中国政策",
     "url": _gnews("国务院 OR 央行 OR 发改委 政策", "zh-CN", "CN", "CN:zh-Hans")},
    {"category": "policy", "country": "US", "name": "美国政策 (Federal Register)",
     "url": "FEDERAL_REGISTER"},  # special handler
    {"category": "policy", "country": "US", "name": "美国政策 (新闻)",
     "url": _gnews("White House OR Congress OR Federal Reserve policy", "en-US", "US", "US:en")},
    {"category": "policy", "country": "JP", "name": "日本政策", "translate": True,
     "url": _gnews("政府 OR 日銀 政策", "ja", "JP", "JP:ja")},
    {"category": "policy", "country": "KR", "name": "韩国政策", "translate": True,
     "url": _gnews("정부 OR 한국은행 정책", "ko", "KR", "KR:ko")},
    {"category": "policy", "country": "EU", "name": "欧盟政策",
     "url": _gnews("European Commission OR ECB policy", "en-GB", "GB", "GB:en")},

    # ---- Tech: 大型公司突破技术 ----
    {"category": "tech", "country": "global", "name": "MIT Technology Review",
     "url": "https://www.technologyreview.com/feed/"},
    {"category": "tech", "country": "global", "name": "Ars Technica",
     "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"category": "tech", "country": "global", "name": "The Verge",
     "url": "https://www.theverge.com/rss/index.xml"},
    {"category": "tech", "country": "global", "name": "突破技术 (新闻)",
     "url": _gnews("breakthrough OR launches OR unveils AI OR chip OR quantum", "en-US", "US", "US:en")},

    # ---- Breaking: 紧急/突发新闻 ----
    {"category": "breaking", "country": "global", "name": "Reuters World (新闻)",
     "url": _gnews("breaking news", "en-US", "US", "US:en")},
    {"category": "breaking", "country": "global", "name": "全球突发 (中文)",
     "url": _gnews("突发 OR 紧急", "zh-CN", "CN", "CN:zh-Hans")},
]

# ---------------------------------------------------------------------------
# 5) Sector sentiment (板块情绪).
#    小红书/抖音没有免费公开 API，这里用可免费获取的替代情绪指标：
#    - A股: 东方财富行业板块的涨跌幅/换手率/涨跌家数/主力资金流（散户情绪代理）
#    - 美股: CNN Fear & Greed 指数 + 行业 ETF 的 RSI/量能/动量
#    情绪分 0-100：>= SELL 阈值视为“过热，提示卖出”；<= BUY 阈值视为“恐慌
#    /割肉，提示买入”。
# ---------------------------------------------------------------------------
SENTIMENT_SELL_SCORE = 75
SENTIMENT_BUY_SCORE = 25

US_SECTOR_ETFS = [
    {"symbol": "XLK",  "name": "科技"},
    {"symbol": "SMH",  "name": "半导体"},
    {"symbol": "XLC",  "name": "通信服务"},
    {"symbol": "XLF",  "name": "金融"},
    {"symbol": "XLE",  "name": "能源"},
    {"symbol": "XLV",  "name": "医疗保健"},
    {"symbol": "XLY",  "name": "可选消费"},
    {"symbol": "XLP",  "name": "必选消费"},
    {"symbol": "XLI",  "name": "工业"},
    {"symbol": "XLB",  "name": "材料"},
    {"symbol": "XLRE", "name": "房地产"},
    {"symbol": "XLU",  "name": "公用事业"},
]

# ---------------------------------------------------------------------------
# 6) Crypto trading signals (BTC/ETH/SOL).
#    K线优先 Binance，失败则回退 OKX；永续资金费率/持仓量/多空比同理；
#    期权 Put/Call 比来自 Deribit。均为免费公开接口。
# ---------------------------------------------------------------------------
CRYPTO_SYMBOLS = [
    {"symbol": "BTC", "name": "比特币",  "binance": "BTCUSDT", "okx": "BTC-USDT", "deribit": "BTC"},
    {"symbol": "ETH", "name": "以太坊",  "binance": "ETHUSDT", "okx": "ETH-USDT", "deribit": "ETH"},
    {"symbol": "SOL", "name": "Solana", "binance": "SOLUSDT", "okx": "SOL-USDT", "deribit": "SOL"},
]

# Keywords that flag a breaking item as "urgent" (for visual highlight).
URGENT_KEYWORDS = [
    "breaking", "urgent", "alert", "evacuat", "earthquake", "explosion",
    "突发", "紧急", "地震", "爆炸", "warning", "crash", "killed", "attack",
]
