"use strict";

const FILTERS = { category: "", country: "" };
const REFRESH_MS = 60 * 1000;
let modalChart = null;

// ---------------------------------------------------------------- helpers
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function fmtNum(n) {
  if (n == null) return "—";
  if (Math.abs(n) >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function timeAgo(ts) {
  if (!ts) return "";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return "刚刚";
  if (s < 3600) return Math.floor(s / 60) + " 分钟前";
  if (s < 86400) return Math.floor(s / 3600) + " 小时前";
  return Math.floor(s / 86400) + " 天前";
}

function sparkline(canvas, series, up) {
  const ctx = canvas.getContext("2d");
  const vals = series.map((p) => p.value);
  new Chart(ctx, {
    type: "line",
    data: {
      labels: series.map((p) => p.date),
      datasets: [{
        data: vals,
        borderColor: up ? "#2ecc71" : "#ff5b5b",
        borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}

// ---------------------------------------------------------------- dashboard
async function loadMetrics() {
  let data;
  try {
    data = await (await fetch("/api/metrics")).json();
  } catch (e) { return; }

  renderMarketCards(data.market || []);
  renderTrends(data.trends || []);
  renderMacro(data.worldbank || []);

  const u = data.updated || {};
  const last = Math.max(u.market || 0, u.worldbank || 0, u.trends || 0);
  $("#updated").textContent = last ? "数据更新于 " + timeAgo(last) : "数据加载中…";
}

function renderMarketCards(items) {
  const el = $("#market-cards");
  if (!items.length) { el.innerHTML = '<p class="muted">市场数据加载中…</p>'; return; }
  el.innerHTML = "";
  items.forEach((m) => {
    const up = m.change_pct >= 0;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <span class="group">${m.group}</span>
      <div class="name">${m.name}</div>
      <div class="value">${fmtNum(m.latest)}</div>
      <div class="change ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(m.change_pct)}%</div>
      <div class="asof">${m.asof}</div>
      <div class="spark"><canvas></canvas></div>`;
    card.addEventListener("click", () => openChart(m.name, m.series));
    el.appendChild(card);
    sparkline(card.querySelector("canvas"), m.series, up);
  });
}

function renderTrends(items) {
  const el = $("#trends-cards");
  const empty = $("#trends-empty");
  if (!items.length) { el.innerHTML = ""; empty.classList.remove("hidden"); return; }
  empty.classList.add("hidden");
  el.innerHTML = "";
  items.forEach((t) => {
    const up = t.change_pct >= 0;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="name">🔍 ${t.keyword}</div>
      <div class="value">${t.latest}</div>
      <div class="change ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(t.change_pct)}%</div>
      <div class="asof">${t.asof}</div>
      <div class="spark"><canvas></canvas></div>`;
    card.addEventListener("click", () => openChart("搜索指数: " + t.keyword, t.series));
    el.appendChild(card);
    sparkline(card.querySelector("canvas"), t.series, up);
  });
}

function renderMacro(items) {
  const el = $("#macro-table");
  if (!items.length) { el.innerHTML = '<p class="muted">宏观数据加载中…</p>'; return; }
  // pivot: rows = country, cols = indicator
  const indicators = [...new Set(items.map((i) => i.indicator))];
  const countries = [...new Set(items.map((i) => i.country))];
  const lookup = {};
  items.forEach((i) => { lookup[i.country + "|" + i.indicator] = i; });

  let html = "<table><thead><tr><th>经济体</th>";
  indicators.forEach((ind) => { html += `<th>${ind}</th>`; });
  html += "</tr></thead><tbody>";
  countries.forEach((c) => {
    html += `<tr><td>${c}</td>`;
    indicators.forEach((ind) => {
      const it = lookup[c + "|" + ind];
      html += it
        ? `<td><span class="macro-val" data-c="${c}" data-i="${ind}">${fmtNum(it.latest)}</span> <span class="muted">'${it.asof.slice(2)}</span></td>`
        : "<td>—</td>";
    });
    html += "</tr>";
  });
  html += "</tbody></table>";
  el.innerHTML = html;
  el.querySelectorAll(".macro-val").forEach((span) => {
    span.style.cursor = "pointer";
    span.style.color = "var(--accent)";
    span.addEventListener("click", () => {
      const it = lookup[span.dataset.c + "|" + span.dataset.i];
      openChart(span.dataset.c + " · " + span.dataset.i, it.series);
    });
  });
}

function openChart(title, series) {
  $("#modal-title").textContent = title;
  $("#chart-modal").classList.remove("hidden");
  if (modalChart) modalChart.destroy();
  const ctx = $("#modal-chart").getContext("2d");
  modalChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: series.map((p) => p.date),
      datasets: [{
        label: title, data: series.map((p) => p.value),
        borderColor: "#4a9eff", borderWidth: 2, pointRadius: 0, tension: 0.2,
        fill: true, backgroundColor: "rgba(74,158,255,.08)",
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8b97a7", maxTicksLimit: 8 }, grid: { color: "#2c3643" } },
        y: { ticks: { color: "#8b97a7" }, grid: { color: "#2c3643" } },
      },
    },
  });
}

// ---------------------------------------------------------------- sentiment
const SIG_LABEL = { sell: "提示卖出", buy: "提示买入", hold: "中性" };

function pctCell(v, digits = 2) {
  if (v == null) return "—";
  const cls = v >= 0 ? "up" : "down";
  return `<span class="${cls}">${v >= 0 ? "+" : ""}${v.toFixed(digits)}%</span>`;
}

function scoreBar(score) {
  const color = score >= 75 ? "var(--down)" : score <= 25 ? "var(--up)" : "var(--accent)";
  return `
    <div class="score-cell">
      <span class="score-num">${score}</span>
      <div class="score-bar"><div style="width:${score}%;background:${color}"></div></div>
    </div>`;
}

function sigBadge(sig) {
  return `<span class="sig sig-${sig}">${SIG_LABEL[sig] || sig}</span>`;
}

async function loadSentiment() {
  let data;
  try {
    data = await (await fetch("/api/sentiment")).json();
  } catch (e) { return; }
  renderCnSentiment(data.cn_sectors || []);
  renderUsSentiment(data.us_sectors || [], data.us_fear_greed);
}

function renderCnSentiment(items) {
  const summary = $("#cn-sentiment-summary");
  const el = $("#cn-sentiment-table");
  if (!items.length) {
    el.innerHTML = '<p class="muted">板块数据加载中…（首次启动约1分钟）</p>';
    summary.innerHTML = "";
    return;
  }
  const hot = items.filter((i) => i.signal === "sell").length;
  const fear = items.filter((i) => i.signal === "buy").length;
  summary.innerHTML = `
    <span class="sent-stat"><b class="down">${hot}</b> 个板块情绪过热（提示卖出）</span>
    <span class="sent-stat"><b class="up">${fear}</b> 个板块恐慌/割肉（提示买入）</span>
    <span class="sent-stat muted">共 ${items.length} 个行业板块</span>`;

  let html = `<table class="sent-table"><thead><tr>
    <th>板块</th><th>情绪分</th><th>信号</th><th>今日</th><th>5日</th>
    <th>换手率</th><th>主力净流入占比</th><th>涨/跌家数</th></tr></thead><tbody>`;
  items.forEach((s) => {
    html += `<tr class="row-${s.signal}">
      <td>${s.name}</td>
      <td>${scoreBar(s.score)}</td>
      <td>${sigBadge(s.signal)}</td>
      <td>${pctCell(s.chg)}</td>
      <td>${pctCell(s.chg5)}</td>
      <td>${s.turnover != null ? s.turnover.toFixed(2) + "%" : "—"}</td>
      <td>${pctCell(s.flow_pct)}</td>
      <td><span class="up">${s.up}</span> / <span class="down">${s.down}</span></td>
    </tr>`;
  });
  el.innerHTML = html + "</tbody></table>";
}

function renderUsSentiment(items, fng) {
  const fngEl = $("#us-fng");
  if (fng) {
    fngEl.innerHTML = `
      <span class="sent-stat">CNN Fear &amp; Greed:
        <b>${fng.score}</b> · ${fng.rating_zh}
        ${fng.score >= 75 ? sigBadge("sell") : fng.score <= 25 ? sigBadge("buy") : ""}
      </span>`;
  } else {
    fngEl.innerHTML = '<span class="sent-stat muted">CNN Fear & Greed 暂未拉到</span>';
  }
  const el = $("#us-sentiment-table");
  if (!items.length) {
    el.innerHTML = '<p class="muted">美股板块数据加载中…</p>';
    return;
  }
  let html = `<table class="sent-table"><thead><tr>
    <th>板块</th><th>ETF</th><th>情绪分</th><th>信号</th>
    <th>RSI14</th><th>5日</th><th>20日</th><th>量能比</th></tr></thead><tbody>`;
  items.forEach((s) => {
    html += `<tr class="row-${s.signal}">
      <td>${s.name}</td>
      <td class="muted">${s.symbol}</td>
      <td>${scoreBar(s.score)}</td>
      <td>${sigBadge(s.signal)}</td>
      <td>${s.rsi != null ? s.rsi : "—"}</td>
      <td>${pctCell(s.chg5)}</td>
      <td>${pctCell(s.chg20)}</td>
      <td>${s.vol_ratio != null ? s.vol_ratio.toFixed(2) : "—"}</td>
    </tr>`;
  });
  el.innerHTML = html + "</tbody></table>";
}

// ---------------------------------------------------------------- crypto
const VERDICT_CLS = {
  long: "v-long", lean_long: "v-lean-long", neutral: "v-neutral",
  lean_short: "v-lean-short", short: "v-short",
};

function fmtPrice(p) {
  if (p == null) return "—";
  return p >= 1000
    ? p.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : p.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

async function loadCrypto() {
  let data;
  try {
    data = await (await fetch("/api/crypto")).json();
  } catch (e) { return; }
  renderCrypto(data.coins || [], data.fear_greed);
}

function renderCrypto(coins, fng) {
  const fngEl = $("#crypto-fng");
  if (fng) {
    fngEl.innerHTML = `
      <span class="sent-stat">Crypto Fear &amp; Greed:
        <b>${fng.value}</b> · ${fng.label_zh}
        ${fng.value >= 75 ? sigBadge("sell") : fng.value <= 25 ? sigBadge("buy") : ""}
      </span>`;
  } else {
    fngEl.innerHTML = "";
  }

  const el = $("#crypto-cards");
  if (!coins.length) {
    el.innerHTML = '<p class="muted">Crypto 数据加载中…（首次启动约1分钟；若持续为空，可能是所在网络无法访问 Binance/OKX）</p>';
    return;
  }
  el.innerHTML = "";
  coins.forEach((c) => {
    const up = c.chg24h >= 0;
    const card = document.createElement("div");
    card.className = "crypto-card";
    card.innerHTML = `
      <div class="crypto-head">
        <div>
          <span class="crypto-sym">${c.symbol}</span>
          <span class="muted">${c.name}</span>
        </div>
        <span class="verdict ${VERDICT_CLS[c.verdict] || ""}">${c.verdict_label} · ${c.score > 0 ? "+" : ""}${c.score}</span>
      </div>
      <div class="crypto-price">
        <span class="value">$${fmtPrice(c.price)}</span>
        <span class="change ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(c.chg24h)}% (24h)</span>
      </div>
      <div class="crypto-grid">
        <div><span class="k">MA30</span><span class="v">${fmtPrice(c.ma30)}</span></div>
        <div><span class="k">MA60</span><span class="v">${fmtPrice(c.ma60)}</span></div>
        <div><span class="k">RSI14</span><span class="v">${c.rsi ?? "—"}</span></div>
        <div><span class="k">MACD柱</span><span class="v">${c.macd_hist ?? "—"}</span></div>
        <div><span class="k">支撑位</span><span class="v up">${fmtPrice(c.support)}</span></div>
        <div><span class="k">压力位</span><span class="v down">${fmtPrice(c.resistance)}</span></div>
        <div><span class="k">资金费率/8h</span><span class="v">${c.funding != null ? (c.funding * 100).toFixed(4) + "%" : "—"}</span></div>
        <div><span class="k">持仓量7日</span><span class="v">${c.oi_chg7d != null ? (c.oi_chg7d >= 0 ? "+" : "") + c.oi_chg7d + "%" : "—"}</span></div>
        <div><span class="k">多空账户比</span><span class="v">${c.long_short ?? "—"}</span></div>
        <div><span class="k">期权P/C比</span><span class="v">${c.pcr ?? "—"}</span></div>
      </div>
      <ul class="crypto-reasons">
        ${c.reasons.map((r) => `<li>${r}</li>`).join("")}
      </ul>
      <div class="muted crypto-chart-hint">点击查看日线 + MA30/MA60 →</div>`;
    card.addEventListener("click", () => openCryptoChart(c));
    el.appendChild(card);
  });
}

function openCryptoChart(c) {
  $("#modal-title").textContent = `${c.symbol}/USDT 日线 · MA30 · MA60`;
  $("#chart-modal").classList.remove("hidden");
  if (modalChart) modalChart.destroy();
  const ctx = $("#modal-chart").getContext("2d");
  const s = c.series;
  modalChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: s.dates,
      datasets: [
        { label: "收盘", data: s.close, borderColor: "#4a9eff", borderWidth: 2,
          pointRadius: 0, tension: 0.2, fill: true, backgroundColor: "rgba(74,158,255,.08)" },
        { label: "MA30", data: s.ma30, borderColor: "#f5a623", borderWidth: 1.5,
          pointRadius: 0, tension: 0.2 },
        { label: "MA60", data: s.ma60, borderColor: "#b06ef5", borderWidth: 1.5,
          pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true, labels: { color: "#8b97a7" } } },
      scales: {
        x: { ticks: { color: "#8b97a7", maxTicksLimit: 8 }, grid: { color: "#2c3643" } },
        y: { ticks: { color: "#8b97a7" }, grid: { color: "#2c3643" } },
      },
    },
  });
}

// ---------------------------------------------------------------- gold
async function loadGold() {
  let data;
  try {
    data = await (await fetch("/api/gold")).json();
  } catch (e) { return; }
  renderGold(data);
  loadGoldNews();
}

function goldCard({ label, value, sub, chg, series, onClick }) {
  const card = document.createElement("div");
  card.className = "card";
  const up = (chg ?? 0) >= 0;
  card.innerHTML = `
    <div class="name">${label}</div>
    <div class="value">${value}</div>
    ${chg != null ? `<div class="change ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(chg)}%</div>` : ""}
    <div class="asof">${sub || ""}</div>
    <div class="spark"><canvas></canvas></div>`;
  if (onClick) card.addEventListener("click", onClick);
  if (series && series.length) sparkline(card.querySelector("canvas"), series, up);
  return card;
}

function renderGold(data) {
  const obsEl = $("#gold-obs");
  const obs = data.observations || [];
  obsEl.innerHTML = obs.length
    ? obs.map((o) => `<li>${o}</li>`).join("")
    : '<li class="muted">数据加载中…（首次启动约1分钟）</li>';

  const el = $("#gold-cards");
  el.innerHTML = "";
  const g = data.gold;
  if (g) {
    const trend = g.price > g.ma30 && g.ma30 > g.ma60 ? "多头排列"
      : g.price < g.ma30 && g.ma30 < g.ma60 ? "空头排列"
      : g.price > g.ma30 ? "MA30上方" : "MA30下方";
    el.appendChild(goldCard({
      label: "🥇 黄金 (COMEX GC=F)",
      value: fmtNum(g.price),
      chg: g.chg,
      sub: `MA30 ${fmtNum(g.ma30)} · MA60 ${fmtNum(g.ma60)} · ${trend} · ${g.asof}`,
      series: g.series.dates.map((d, i) => ({ date: d, value: g.series.close[i] })),
      onClick: () => openGoldChart(g),
    }));
  }
  const dxy = data.dxy;
  if (dxy) {
    el.appendChild(goldCard({
      label: "💵 美元指数 (DXY)",
      value: fmtNum(dxy.price),
      chg: dxy.chg,
      sub: `5日 ${dxy.chg5 >= 0 ? "+" : ""}${dxy.chg5}% · 20日 ${dxy.chg20 >= 0 ? "+" : ""}${dxy.chg20}% · ${dxy.asof}`,
      series: dxy.series,
      onClick: () => openChart("美元指数 DXY", dxy.series),
    }));
  }
  const t = data.us10y;
  if (t) {
    el.appendChild(goldCard({
      label: "🏛 美债10年收益率 (%)",
      value: fmtNum(t.price),
      chg: t.chg,
      sub: `5日 ${t.chg5 >= 0 ? "+" : ""}${t.chg5}% · ${t.asof}`,
      series: t.series,
      onClick: () => openChart("美债10年收益率", t.series),
    }));
  }
  const c = data.cot;
  if (c) {
    el.appendChild(goldCard({
      label: "📊 COMEX 投机净多头 (手)",
      value: fmtNum(c.net),
      chg: null,
      sub: `周变化 ${c.net_chg >= 0 ? "+" : ""}${fmtNum(c.net_chg)} · 多 ${fmtNum(c.long)} / 空 ${fmtNum(c.short)} · ${c.asof}`,
      series: c.series,
      onClick: () => openChart("COMEX 黄金投机净多头 (52周)", c.series),
    }));
  }
  if (!el.children.length) {
    el.innerHTML = '<p class="muted">黄金数据加载中…</p>';
  }
}

function openGoldChart(g) {
  $("#modal-title").textContent = "黄金 GC=F 日线 · MA30 · MA60";
  $("#chart-modal").classList.remove("hidden");
  if (modalChart) modalChart.destroy();
  const ctx = $("#modal-chart").getContext("2d");
  const s = g.series;
  modalChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: s.dates,
      datasets: [
        { label: "收盘", data: s.close, borderColor: "#e8c15a", borderWidth: 2,
          pointRadius: 0, tension: 0.2, fill: true, backgroundColor: "rgba(232,193,90,.08)" },
        { label: "MA30", data: s.ma30, borderColor: "#4a9eff", borderWidth: 1.5,
          pointRadius: 0, tension: 0.2 },
        { label: "MA60", data: s.ma60, borderColor: "#b06ef5", borderWidth: 1.5,
          pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true, labels: { color: "#8b97a7" } } },
      scales: {
        x: { ticks: { color: "#8b97a7", maxTicksLimit: 8 }, grid: { color: "#2c3643" } },
        y: { ticks: { color: "#8b97a7" }, grid: { color: "#2c3643" } },
      },
    },
  });
}

async function loadGoldNews() {
  let data;
  try {
    data = await (await fetch("/api/news?category=fed&limit=30")).json();
  } catch (e) { return; }
  const el = $("#gold-news");
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="empty">暂无美联储新闻（每 10 分钟刷新）</div>';
    return;
  }
  el.innerHTML = "";
  items.forEach((n) => {
    const div = document.createElement("div");
    div.className = "news-item";
    div.innerHTML = `
      <div class="news-badges"><span class="badge fed">美联储</span></div>
      <div class="news-body">
        <div class="news-title">
          <a href="${n.link}" target="_blank" rel="noopener">${n.title}</a>
        </div>
        <div class="news-meta">${n.source} · ${timeAgo(n.published || n.fetched)}</div>
      </div>`;
    el.appendChild(div);
  });
}

// ---------------------------------------------------------------- news feed
async function loadNews() {
  const qs = new URLSearchParams();
  if (FILTERS.category) qs.set("category", FILTERS.category);
  if (FILTERS.country) qs.set("country", FILTERS.country);
  let data;
  try {
    data = await (await fetch("/api/news?" + qs.toString())).json();
  } catch (e) { return; }
  renderNews(data.items || []);
}

const CAT_LABEL = { policy: "政策", tech: "科技", breaking: "突发", fed: "美联储" };

function renderNews(items) {
  const el = $("#news-list");
  if (!items.length) { el.innerHTML = '<div class="empty">暂无消息（数据每 10 分钟刷新一次）</div>'; return; }
  el.innerHTML = "";
  items.forEach((n) => {
    const div = document.createElement("div");
    div.className = "news-item" + (n.urgent ? " urgent" : "");
    const ts = n.published || n.fetched;
    // Google News RSS summaries are usually just the title again — hide those.
    const dupSummary = n.summary && n.title &&
      n.title.replace(/\s+/g, "").startsWith(n.summary.replace(/\s+/g, "").slice(0, 12));
    const summary = dupSummary ? "" : n.summary;
    div.innerHTML = `
      <div class="news-badges">
        <span class="badge ${n.category}">${CAT_LABEL[n.category] || n.category}</span>
        <span class="badge">${n.country}</span>
      </div>
      <div class="news-body">
        <div class="news-title">
          <a href="${n.link}" target="_blank" rel="noopener">${n.title}</a>
          ${n.urgent ? '<span class="urgent-flag">⚠ 紧急</span>' : ""}
        </div>
        <div class="news-meta">${n.source} · ${timeAgo(ts)}</div>
        ${summary ? `<div class="news-summary">${summary}</div>` : ""}
      </div>`;
    el.appendChild(div);
  });
}

// ---------------------------------------------------------------- wiring
function initTabs() {
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".tab").forEach((t) => t.classList.remove("active"));
      $$(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $("#" + tab.dataset.tab).classList.add("active");
      // 切换 tab 时立即刷新一次，避免首屏“加载中”停留太久
      if (tab.dataset.tab === "sentiment") loadSentiment();
      if (tab.dataset.tab === "crypto") loadCrypto();
      if (tab.dataset.tab === "gold") loadGold();
    });
  });
}

function initFilters() {
  $$(".filter-group").forEach((group) => {
    const key = group.dataset.filter;
    group.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        group.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        FILTERS[key] = chip.dataset.value;
        loadNews();
      });
    });
  });
}

function initModal() {
  $("#modal-close").addEventListener("click", () => $("#chart-modal").classList.add("hidden"));
  $("#chart-modal").addEventListener("click", (e) => {
    if (e.target.id === "chart-modal") $("#chart-modal").classList.add("hidden");
  });
}

function tickClock() {
  $("#clock").textContent = new Date().toLocaleString("zh-CN", { hour12: false });
}

function init() {
  initTabs();
  initFilters();
  initModal();
  tickClock();
  setInterval(tickClock, 1000);
  loadMetrics();
  loadNews();
  loadSentiment();
  loadCrypto();
  loadGold();
  setInterval(loadMetrics, REFRESH_MS);
  setInterval(loadNews, REFRESH_MS);
  setInterval(loadSentiment, REFRESH_MS * 2);
  setInterval(loadCrypto, REFRESH_MS * 2);
  setInterval(loadGold, REFRESH_MS * 2);
}

document.addEventListener("DOMContentLoaded", init);
