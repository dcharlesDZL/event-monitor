# Event Monitor · 数据看板 + 消息流

一个自带后端的单页网站:左边「数据看板」看经济/市场/搜索指数,右边「消息流」看各国政策、科技突破、突发新闻。全部使用**免费公开数据源,无需任何 API Key**,开箱即跑。

![tabs](数据看板 / 消息流)

## 快速开始

```bash
./run.sh
```

首次运行会自动创建虚拟环境、装依赖、启动服务。然后浏览器打开:

> http://127.0.0.1:8000

数据在后台定时拉取(市场每 30 分钟、新闻每 10 分钟、搜索指数每小时),页面每 60 秒自动刷新。

手动启动(如果不想用脚本):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn main:app --port 8000
```

## 功能

### 数据看板
| 模块 | 数据源 | 内容 |
|------|--------|------|
| 市场/汇率/大宗商品 | Yahoo Finance (免费) | 美股、亚太股市、欧股、美债收益率、美元/人民币/欧元/日元、黄金、原油、比特币。卡片带迷你走势图,点开看大图。 |
| 搜索指数 | Google Trends (pytrends,非官方) | 关键词热度。**best-effort**,可能被限流,拉不到时显示提示并每小时重试。 |
| 宏观经济 | World Bank API (免费) | 中/美/日/韩/欧元区的 GDP 增速、CPI、失业率。 |

### 消息流
| 类别 | 数据源 |
|------|--------|
| 政策 (中/美/日/韩/欧) | Google News RSS 各语言查询 + 美国 Federal Register API |
| 科技突破 | MIT Tech Review、Ars Technica、The Verge、Google News 关键词 |
| 突发新闻 | Google News RSS(中英文)|

- 支持按 **类别 + 地区** 双重筛选。
- 含「紧急」关键词(breaking/紧急/地震/爆炸…)的条目高亮标红。
- 新闻按链接去重,存 SQLite,重启不丢;自动只保留最近 2000 条。

### 板块情绪
反向情绪信号:**情绪过热(≥75)提示卖出、恐慌割肉(≤25)提示买入**。小红书/抖音无公开接口,情绪分由免费替代指标合成:

| 市场 | 数据源 | 指标 |
|------|--------|------|
| A股行业板块 | 东方财富 (免费) | 涨跌幅(今日/5日/10日)、换手率、涨跌家数、主力资金净流入。绝对情绪(60%) + 全市场横截面排名(40%),避免普涨/普跌日全部同向。 |
| 美股 | CNN Fear & Greed + Yahoo Finance | 恐贪指数 + 12 只行业 ETF (XLK/SMH/XLF…) 的 RSI14、5/20日动量、量能比。 |

### Crypto 交易 (BTC / ETH / SOL)
现货、永续、期权三个市场综合打分,给出 **做多 / 谨慎偏多 / 观望 / 谨慎偏空 / 做空** 建议 + 理由列表:

| 维度 | 数据源 | 指标 |
|------|--------|------|
| 技术面 | Binance 日K (失败自动回退 OKX) | MA30/MA60 排列、RSI14、MACD、摆动点聚类支撑/压力位 |
| 永续合约 | Binance fapi (回退 OKX) | 资金费率(拥挤度反向)、持仓量 7 日变化、多空账户比(极端反向) |
| 期权 | Deribit (免费) | Put/Call 持仓比(极端反向) |
| 整体情绪 | alternative.me | Crypto Fear & Greed 指数 |

点卡片可看日线 + MA30/MA60 大图。信号仅供参考,不构成投资建议。

### 黄金监控
影响黄金的核心变量集中在一屏:

| 模块 | 数据源 | 内容 |
|------|--------|------|
| 金价 | Yahoo Finance (GC=F) | 日线 + MA30/MA60 排列判断,点卡片看均线大图 |
| 美元指数 | Yahoo Finance (DX-Y.NYB) | DXY 现值 + 5/20日变化(美元强弱与金价负相关) |
| 美债10年收益率 | Yahoo Finance (^TNX) | 利率上行利空黄金 |
| COMEX 持仓 | CFTC 官方 COT 报告 (免费 API) | 投机(非商业)净多头 52 周序列、周变化、多空持仓;接近 52 周高/低位时给出拥挤度提示 |
| 美联储动态 | Google News (中英文) | 加息/降息/利率决议/鲍威尔相关新闻,也可在消息流 tab 按「美联储」筛选 |

页面顶部有「综合观察」:均线排列、美元/利率 5 日方向、投机持仓变化的自动解读。

## 项目结构

```
event-monitor/
├── run.sh                 # 一键启动
├── requirements.txt
├── backend/
│   ├── main.py            # FastAPI:API + 托管前端
│   ├── config.py          # ★ 所有数据源配置都在这里(改这里即可增删源)
│   ├── scheduler.py       # 后台定时刷新线程
│   ├── db.py              # SQLite(新闻存储/去重)
│   └── collectors/
│       ├── metrics.py     # Yahoo / World Bank / Google Trends
│       ├── news.py        # RSS + Federal Register
│       ├── sentiment.py   # A股/美股板块情绪 (东方财富 / CNN / Yahoo)
│       ├── crypto.py      # BTC/ETH/SOL 信号 (Binance/OKX/Deribit)
│       └── gold.py        # 黄金监控 (Yahoo / CFTC COT)
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js             # Chart.js 看板 + 消息流渲染
```

## 怎么改 / 加数据源

全部集中在 [`backend/config.py`](backend/config.py):

- **加一只指数/汇率/商品**:往 `MARKET_SERIES` 加一行,`symbol` 用 Yahoo Finance 代码(如 `^FTSE`、`SI=F` 白银)。
- **加一个国家的宏观指标**:改 `WORLDBANK_COUNTRIES` 或 `WORLDBANK_INDICATORS`(指标代码见 World Bank)。
- **加搜索关键词**:改 `TRENDS_KEYWORDS`。
- **加新闻/政策源**:往 `NEWS_FEEDS` 加一条 `{category, country, name, url}`。普通 RSS 直接填 URL;Google News 用 `_gnews(query, hl, gl, ceid)` 生成。
- **调刷新频率**:改顶部的 `*_REFRESH_SEC`。
- **改紧急关键词**:改 `URGENT_KEYWORDS`。

改完重启服务即可生效。

## API

| 路径 | 说明 |
|------|------|
| `GET /api/metrics` | 市场 + 宏观 + 搜索指数(含完整时间序列) |
| `GET /api/news?category=&country=&limit=` | 新闻列表,支持筛选 |
| `GET /api/sentiment` | A股/美股板块情绪分 + CNN Fear & Greed |
| `GET /api/crypto` | BTC/ETH/SOL 综合信号(技术面+永续+期权) |
| `GET /api/gold` | 黄金监控(金价均线、DXY、美债收益率、COT 持仓、综合观察) |
| `GET /api/health` | 健康检查 |

## 备注

- **Stooq 已弃用**:原计划用 Stooq CSV,但它现在加了 JS 反爬,服务端拿不到数据,已改用 Yahoo Finance。
- **Google Trends 不稳定**:pytrends 是非官方库,Google 经常限流。它拉不到不影响其它功能。若长期拿不到可考虑去掉(从 requirements 删 `pytrends`)。
- **Crypto 数据依赖网络环境**:Binance/OKX/Deribit 在部分地区(如中国大陆、美国)需科学上网才能访问;拉不到时该 tab 会显示提示,不影响其它功能。
- 想长期后台运行,可把 `uvicorn` 挂到 `launchd` / `systemd` / `tmux`,或用 `--host 0.0.0.0` 暴露给局域网。
