"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1) => x == null ? "–" : `<span class="${x >= 0 ? "up" : "down"}">${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%</span>`;
const num = (x, d = 2) => x == null ? "–" : Number(x).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const cls = s => /^BUY|ACCUM|SIP/.test(s) ? "BUY" : /SELL/.test(s) ? "SELL" : "HOLD";
const chip = s => `<span class="chip ${cls(s)}">${esc(s)}</span>`;
const bar = v => `<span class="bar-s" style="width:${Math.max(2, v * 0.6)}px"></span>${v.toFixed(0)}`;
let D = null, TR = null, HIST = [], UNI = null, MODES = null, IDX = null, BT = null, BRIEF = null, tab = "today";
const sortState = {};
const LS = { get: k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };
const watch = () => LS.get("watchlist") || [];
const inWatch = s => watch().includes(s);
const toggleWatch = s => { const w = watch(); const i = w.indexOf(s); i >= 0 ? w.splice(i, 1) : w.push(s); LS.set("watchlist", w); };

const TABS = [["today", "Today"], ["trading", "Trading"], ["investing", "Investing"], ["overview", "Overview"], ["search", "All stocks"], ["watchlist", "Watchlist"], ["stocks", "India stocks"], ["funds", "Mutual funds"], ["metals", "Gold, silver & commodities"],
["fx", "Currency & bonds"], ["global", "Global markets"], ["ipo", "IPOs"], ["track", "Track record"], ["backtest", "Backtest"], ["news", "News"], ["how", "How it works"]];
const BOTTOM = [["today", "Today", "★"], ["trading", "Trading", "⚡"], ["investing", "Investing", "◈"], ["markets", "Markets", "🌐"], ["more", "More", "☰"]];
const SECTIONS = { markets: "metals", more: "search" };  // bottom-nav groups map to a starting tab

async function load() {
  try {
    const t = Date.now();
    D = await (await fetch("data/latest.json?" + t)).json();
    try { TR = await (await fetch("data/track_record.json?" + t)).json(); } catch { TR = { picks: [], summary: {} }; }
    try { HIST = await (await fetch("data/history.json?" + t)).json(); } catch { HIST = []; }
    try { UNI = await (await fetch("data/universe.json?" + t)).json(); } catch { UNI = null; }
    try { MODES = await (await fetch("data/modes.json?" + t)).json(); } catch { MODES = null; }
    try { IDX = await (await fetch("data/stocks_index.json?" + t)).json(); } catch { IDX = null; }
    try { BT = await (await fetch("data/backtest.json?" + t)).json(); } catch { BT = null; }
    try { BRIEF = await (await fetch("data/brief.json?" + t)).json(); } catch { BRIEF = null; }
  } catch (e) {
    $("#view").innerHTML = `<div class="card warn">No data yet. Run <code>python pipeline/run_daily.py</code> once, then reload.</div>`; return;
  }
  const g = new Date(D.generated_at);
  const h = UNI && UNI.health;
  const badge = h ? `<span class="chip ${h.status === "ok" ? "BUY" : "HOLD"}" title="${esc((h.issues || []).join("; ") || "Data checks passed")}">${h.status === "ok" ? "✓ data ok" : "⚠ data"}</span> ` : "";
  $("#stamp").innerHTML = badge + "Updated " + g.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) + " · end-of-day data";
  $("#foot").innerHTML = esc(D.disclaimer) + " Data: Yahoo Finance, AMFI via mfapi.in. May be delayed or incomplete.";
  $("#tabs").innerHTML = TABS.map(([k, l]) => `<button data-t="${k}" class="${k === tab ? "on" : ""}">${l}</button>`).join("");
  $("#tabs").onclick = e => { const b = e.target.closest("button"); if (b) go(b.dataset.t); };
  $("#bottomnav").innerHTML = BOTTOM.map(([k, l, ic]) => `<button data-t="${k}"><span class="ic">${ic}</span>${l}</button>`).join("");
  $("#bottomnav").onclick = e => { const b = e.target.closest("button"); if (b) go(SECTIONS[b.dataset.t] || b.dataset.t); };
  load2();
}
function go(t) { tab = t; history.replaceState(null, "", "#" + tab); window.scrollTo(0, 0); load2(); }
function load2() {
  const VIEWS = { today, trading, investing, overview, search, watchlist, stocks, funds, metals, fx, global, ipo, track, backtest, news, how };
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === tab));
  const botActive = Object.keys(SECTIONS).find(k => SECTIONS[k] === tab) || tab;
  document.querySelectorAll("#bottomnav button").forEach(b => b.classList.toggle("on", b.dataset.t === botActive));
  $("#view").innerHTML = (VIEWS[tab] || today)();
  wireTables();
  if (tab === "search") wireSearch();
  if (tab === "trading" || tab === "investing") wireModeTable();
}

function pickCard(p, i) {
  const lv = p.stop_loss ? `<div class="lvl"><span>Buy zone</span><span>${num(p.entry_low)} – ${num(p.entry_high)}</span>
    <span>Stop-loss</span><span class="down">${num(p.stop_loss)}</span><span>Target 1 / 2</span><span class="up">${num(p.target_1)} / ${num(p.target_2)}</span></div>`
    : `<div class="lvl"><span>NAV</span><span>${num(p.price)}</span></div>`;
  return `<div class="card pick"><div class="top"><h3>${i}. ${esc(p.name)}</h3>${chip(p.signal)}</div>
    <div class="muted">${esc(p.kind)} · score ${p.score}</div>${lv}<div class="muted" style="margin-top:6px">${esc(p.reason)}</div></div>`;
}
// ---- inline SVG charts (no external library, works offline) ----
function sparkline(vals, up = true) {
  vals = vals.filter(v => v != null);
  if (vals.length < 2) return `<div class="muted" style="font-size:12px">Trend builds up over the next few days.</div>`;
  const w = 300, h = 60, mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 4 - (v - mn) / rng * (h - 8)).toFixed(1)}`);
  const col = (vals[vals.length - 1] >= vals[0]) === up ? "var(--up)" : "var(--down)";
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline fill="none" stroke="${col}" stroke-width="2" points="${pts.join(" ")}"/>
    <polygon fill="${col}" opacity=".10" points="0,${h} ${pts.join(" ")} ${w},${h}"/></svg>`;
}
function gauge(pct01) {
  const a = Math.PI * (1 - (pct01 ?? 0)), cx = 90, cy = 90, r = 76;
  const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a);
  const col = pct01 > 0.6 ? "var(--up)" : pct01 < 0.4 ? "var(--down)" : "var(--warn)";
  return `<svg viewBox="0 0 180 104" style="width:180px;max-width:60vw">
    <path d="M14 90 A76 76 0 0 1 166 90" fill="none" stroke="var(--line)" stroke-width="14" stroke-linecap="round"/>
    <path d="M14 90 A76 76 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="${col}" stroke-width="14" stroke-linecap="round"/>
    <text x="90" y="80" text-anchor="middle" font-size="26" font-weight="700" fill="var(--ink)">${pct01 == null ? "–" : Math.round(pct01 * 100) + "%"}</text>
    <text x="90" y="98" text-anchor="middle" font-size="11" fill="var(--muted)">above 200-day avg</text></svg>`;
}
function sectorBar(s, maxAbs) {
  const w = Math.min(50, Math.abs(s.avg_day) / maxAbs * 50), pos = s.avg_day >= 0;
  return `<div class="srow"><div>${esc(s.sector)} <span class="muted">(${s.count})</span></div>
    <div class="sbar"><i style="${pos ? "left:50%" : "right:50%"};width:${w}%;background:${pos ? "var(--up)" : "var(--down)"}"></i>
    <b>${pct(s.avg_day)}</b><span class="r muted">score ${s.avg_score}</span></div></div>`;
}

function overview() {
  const o = D.overview;
  if (!o) return `<div class="card">Overview will appear after the next data update.</div>`;
  const total = o.advancers + o.decliners + (o.unchanged || 0);
  const aPct = total ? o.advancers / total * 100 : 50;
  const maxAbs = Math.max(0.001, ...o.sectors.map(s => Math.abs(s.avg_day)));
  const snapCard = (k, v) => v ? `<div class="kpi"><div class="l">${esc(k)}</div><div class="v">${num(v.price, v.price > 500 ? 0 : 2)}</div><div>${pct(v.day)} <span class="muted">1M ${pct(v.ret_1m, 0)}</span></div></div>` : "";
  const mv = (m, sign) => `<div class="mv"><span>${esc(m.name)}</span><span class="${sign}">${pct(m.day)}</span></div>`;
  const regcol = D.regime === "RISK-ON" ? "up" : D.regime === "RISK-OFF" ? "down" : "";
  return `<h2>Market overview</h2>
  <div class="card" style="display:flex;gap:20px;flex-wrap:wrap;align-items:center;justify-content:space-between">
    <div>${gauge(D.breadth_above_200dma)}</div>
    <div style="flex:1;min-width:200px">
      <div class="muted">Regime</div><div class="regime ${regcol}">${D.regime}</div>
      <div class="adc" style="margin-top:10px"><div class="a" style="width:${aPct}%">${o.advancers} up</div><div class="d" style="width:${100 - aPct}%">${o.decliners} down</div></div>
      <div class="muted" style="margin-top:6px">${o.buy_signals} BUY · ${o.sell_signals} SELL signals across ${total} tracked stocks</div>
    </div></div>

  <h2>Snapshot</h2><div class="kpis">${Object.entries(o.snapshot).map(([k, v]) => snapCard(k, v)).join("")}</div>

  <h2>Sector performance (today)</h2><div class="card">${o.sectors.map(s => sectorBar(s, maxAbs)).join("") || "<span class='muted'>No sector data.</span>"}</div>

  <div class="grid">
    <div class="card"><b>Top gainers</b>${o.top_gainers.map(m => mv(m, "up")).join("")}</div>
    <div class="card"><b>Top losers</b>${o.top_losers.map(m => mv(m, "down")).join("")}</div>
  </div>

  <h2>Trends ${HIST.length < 2 ? "<span class='muted' style='font-size:13px'>(fills in over the coming days)</span>" : `<span class="muted" style="font-size:13px">(last ${HIST.length} days)</span>`}</h2>
  <div class="grid">
    ${[["Nifty 50", "nifty", true], ["Sensex", "sensex", true], ["Gold ($)", "gold", true], ["Silver ($)", "silver", true], ["USD/INR", "usdinr", false], ["Market breadth", "breadth", true]]
      .map(([lbl, key, up]) => `<div class="card"><div class="l muted">${lbl}</div>${sparkline(HIST.map(h => h[key]), up)}
        <div class="muted" style="font-size:12px">${HIST.length ? "latest " + num(HIST[HIST.length - 1][key], key === "breadth" ? 2 : 0) : ""}</div></div>`).join("")}
  </div>
  <p class="muted">All figures from the latest end-of-day run. "Market breadth" = share of tracked Indian stocks above their 200-day average (a breadth above ~0.6 is healthy, below ~0.4 is weak).</p>`;
}

// ---------- Trading / Investing modes ----------
function modeCard(r, mode) {
  const vtxt = mode === "trading" ? r.trading_verdict_txt : r.investing_verdict_txt;
  const vc = mode === "trading" ? r.trading_verdict : r.investing_verdict;
  const score = mode === "trading" ? r.trading_score : r.investing_score;
  const lvl = mode === "trading" && r.trading_buy_upto
    ? `<div class="lvl" style="margin-top:6px"><span>Good to buy up to</span><span>₹${num(r.trading_buy_upto)}</span><span>Stop-loss</span><span class="down">₹${num(r.trading_stop)}</span><span>Target 1</span><span class="up">₹${num(r.trading_t1)}</span></div>` : "";
  return `<div class="mode-card ${mode === "trading" ? "trade" : "invest"}" onclick="openStock('${r.symbol}')" style="cursor:pointer">
    <div class="top" style="display:flex;justify-content:space-between;gap:8px"><div><span class="mode-tag ${mode === "trading" ? "trade" : "invest"}">${mode}</span><h3 style="margin:2px 0">${esc(r.name)}</h3><span class="muted">${esc(r.symbol)} · ₹${num(r.close)} ${pct(r.day_change)}</span></div>
    <div style="text-align:right"><div class="vd ${vc}">${esc(vtxt)}</div><div class="muted" style="margin-top:4px">score ${score}</div></div></div>${lvl}</div>`;
}
function modeView(mode) {
  if (!MODES || !IDX) return `<div class="card">Dual-mode scoring appears after the next data update (it seeds over a few runs).</div>`;
  const top = mode === "trading" ? MODES.trading_top5 : MODES.investing_top5;
  const blurb = mode === "trading"
    ? "Swing trades (days to weeks): trend, momentum, volume & delivery. Each pick shows a buy-up-to price, stop-loss, targets and a time-stop."
    : "Long-term (months to years): quality & valuation first, trend only as timing. No tight stop — a thesis-broken condition and a review date instead.";
  return `<h2>${mode === "trading" ? "⚡ Trading" : "◈ Investing"} — Top 5 <span class="muted" style="font-size:13px">(as of ${MODES.asof})</span></h2>
    <p class="muted">${blurb}</p>
    ${top.map(r => modeCard(r, mode)).join("")}
    <h2>All eligible stocks, ranked</h2>
    <p class="muted">${IDX.count} scored. Tap any stock for its chart, reading and levels. Sort by a column header.</p>
    <input id="mq" placeholder="Filter by name or symbol…" style="width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;margin-bottom:8px">
    <div id="mtbl"></div>`;
}
function trading() { return modeView("trading"); }
function investing() { return modeView("investing"); }
function wireModeTable() {
  const mode = tab;
  const scoreKey = mode === "trading" ? "trading_score" : "investing_score";
  const vKey = mode === "trading" ? "trading_verdict" : "investing_verdict";
  const q = $("#mq"), box = $("#mtbl");
  let sortKey = scoreKey, sortDir = -1;
  const vlabel = { buy: "BUY", dip: "DIP", wait: "WAIT" };
  // distinct columns per mode: Trading = setup/levels/momentum; Investing = valuation/quality/horizon
  const cols = mode === "trading" ? [
    { h: "Stock", k: "name", f: r => `<b>${esc(r.symbol)}</b><br><span class="muted" style="font-size:12px">${esc(r.name)}</span>` },
    { h: "₹", k: "close", n: 1, f: r => num(r.close) }, { h: "Day", k: "day_change", n: 1, f: r => pct(r.day_change) },
    { h: "T-score", k: "trading_score", n: 1, f: r => bar(r.trading_score) }, { h: "Call", k: "trading_verdict", f: r => `<span class="vd ${r.trading_verdict}">${vlabel[r.trading_verdict] || "–"}</span>` },
    { h: "Buy ≤", k: "trading_buy_upto", n: 1, f: r => r.trading_buy_upto ? "₹" + num(r.trading_buy_upto) : "–" },
    { h: "R:R", k: "risk_reward", n: 1, f: r => r.risk_reward ?? "–" }, { h: "RSI", k: "rsi", n: 1, f: r => num(r.rsi, 0) },
    { h: "Vol×", k: "vol_surge", n: 1, f: r => r.vol_surge ? r.vol_surge + "×" : "–" },
  ] : [
    { h: "Stock", k: "name", f: r => `<b>${esc(r.symbol)}</b><br><span class="muted" style="font-size:12px">${esc(r.name)}</span>` },
    { h: "₹", k: "close", n: 1, f: r => num(r.close) }, { h: "1Y", k: "ret_1y", n: 1, f: r => pct(r.ret_1y, 0) },
    { h: "I-score", k: "investing_score", n: 1, f: r => bar(r.investing_score) }, { h: "Call", k: "investing_verdict", f: r => `<span class="vd ${r.investing_verdict}">${vlabel[r.investing_verdict] || "–"}</span>` },
    { h: "P/E", k: "pe", n: 1, f: r => r.pe != null ? num(r.pe, 1) : "–" }, { h: "ROE", k: "roe", n: 1, f: r => r.roe != null ? Math.round(r.roe * 100) + "%" : "–" },
    { h: "Growth", k: "rev_growth", n: 1, f: r => r.rev_growth != null ? Math.round(r.rev_growth * 100) + "%" : "–" }, { h: "Sector", k: "sector", f: r => esc(r.sector || "–") },
  ];
  const render = () => {
    const term = (q.value || "").trim().toLowerCase();
    let rows = IDX.rows.filter(r => !term || r.symbol.toLowerCase().includes(term) || (r.name || "").toLowerCase().includes(term));
    rows = [...rows].sort((a, b) => ((a[sortKey] ?? -1) - (b[sortKey] ?? -1)) * sortDir);
    box.innerHTML = `<div class="scroll"><table><thead><tr>${cols.map(c => `<th class="${c.n ? "n" : ""}" data-k="${c.k}">${c.h}</th>`).join("")}</tr></thead><tbody>
      ${rows.slice(0, 150).map(r => `<tr class="row" onclick="openStock('${r.symbol}')">${cols.map(c => `<td class="${c.n ? "n" : ""}">${c.f(r)}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div><div class="muted" style="font-size:12px;margin-top:6px">${rows.length} stocks${rows.length > 150 ? " — showing top 150" : ""}</div>`;
    box.querySelector("thead").onclick = e => { const th = e.target.closest("th"); if (!th) return; const k = th.dataset.k; sortDir = sortKey === k ? -sortDir : -1; sortKey = k; render(); };
  };
  q.oninput = render; render();
}

// ---------- Watchlist ----------
function watchlist() {
  const w = watch();
  if (!w.length) return `<h2>Watchlist</h2><div class="card muted">No stocks yet. Open any stock and tap the ☆ to add it. Saved on this device only.</div>`;
  const rows = (IDX ? IDX.rows : []).filter(r => w.includes(r.symbol));
  const missing = w.filter(s => !rows.find(r => r.symbol === s));
  return `<h2>Watchlist <span class="muted" style="font-size:13px">(${w.length}, on this device)</span></h2>
    ${rows.map(r => modeCard(r, "trading")).join("")}
    ${missing.length ? `<p class="muted">Not in the scored set yet: ${missing.map(s => `<a href="#" onclick="openStock('${s}');return false">${esc(s)}</a>`).join(", ")}</p>` : ""}`;
}

// ---------- chart (TradingView Lightweight Charts, bundled locally, Apache-2.0) ----------
function sma(arr, n) { const o = arr.map(() => null); let s = 0; for (let i = 0; i < arr.length; i++) { s += arr[i]; if (i >= n) s -= arr[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
function buildChart(d) {
  const O = d.ohlc; if (!O || !O.c || !O.c.length) { $("#chart").innerHTML = "<p class='muted'>No chart data.</p>"; return; }
  const dark = matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light";
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const LC = window.LightweightCharts;
  const host = $("#chart"); host.innerHTML = ""; $("#vol").innerHTML = "";
  if (chart) { try { chart.remove(); } catch {} }
  const opts = { layout: { background: { color: "transparent" }, textColor: dark ? "#98a2b3" : "#667085" },
    grid: { vertLines: { color: dark ? "#1f2630" : "#eef2f6" }, horzLines: { color: dark ? "#1f2630" : "#eef2f6" } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false }, crosshair: { mode: 0 },
    autoSize: true };
  chart = LC.createChart(host, opts);
  const vchart = LC.createChart($("#vol"), { ...opts, rightPriceScale: { borderVisible: false }, timeScale: { visible: false } });
  const times = O.t;
  const full = times.map((t, i) => ({ time: t, open: O.o[i], high: O.h[i], low: O.l[i], close: O.c[i], volume: O.v[i] }))
    .filter(x => x.close != null);
  let ranges = { "1M": 22, "3M": 66, "6M": 132, "1Y": 252, "3Y": 756, "Max": full.length };
  let state = { range: "6M", type: "candle", inds: new Set(["sma50", "sma200", "levels"]) };
  const extras = [];
  function draw() {
    // clear extra series
    while (extras.length) { try { chart.removeSeries(extras.pop()); } catch {} }
    host.querySelectorAll(".pl").forEach(n => n.remove());
    const n = ranges[state.range] || full.length;
    const data = full.slice(-n);
    chart._main && (() => { try { chart.removeSeries(chart._main); } catch {} })();
    if (state.type === "candle") {
      chart._main = chart.addCandlestickSeries({ upColor: css("--up"), downColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down"), borderVisible: false });
      chart._main.setData(data.map(x => ({ time: x.time, open: x.open, high: x.high, low: x.low, close: x.close })));
    } else {
      chart._main = chart.addLineSeries({ color: css("--accent"), lineWidth: 2 });
      chart._main.setData(data.map(x => ({ time: x.time, value: x.close })));
    }
    const closes = data.map(x => x.close);
    const addSMA = (len, col) => { const v = sma(closes, len); const s = chart.addLineSeries({ color: col, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }); s.setData(data.map((x, i) => v[i] == null ? null : { time: x.time, value: v[i] }).filter(Boolean)); extras.push(s); };
    if (state.inds.has("sma20")) addSMA(20, "#f59e0b");
    if (state.inds.has("sma50")) addSMA(50, "#3b82f6");
    if (state.inds.has("sma200")) addSMA(200, "#a855f7");
    if (state.inds.has("bb")) { const m = sma(closes, 20); const dev = closes.map((c, i) => { if (i < 19) return null; const sl = closes.slice(i - 19, i + 1), mu = m[i]; return Math.sqrt(sl.reduce((a, b) => a + (b - mu) ** 2, 0) / 20); }); [1, -1].forEach(sgn => { const s = chart.addLineSeries({ color: "#14b8a6", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false }); s.setData(data.map((x, i) => dev[i] == null ? null : { time: x.time, value: m[i] + sgn * 2 * dev[i] }).filter(Boolean)); extras.push(s); }); }
    if (state.inds.has("levels") && d.trading) {
      const T = d.trading;
      [["buy_upto", "#22c55e", "Buy ≤"], ["stop_loss", "#ef4444", "Stop"], ["target_1", "#3b82f6", "T1"], ["target_2", "#6366f1", "T2"]].forEach(([k, col, lbl]) => {
        if (T[k]) chart._main.createPriceLine({ price: T[k], color: col, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: lbl });
      });
    }
    // volume
    vchart._v && (() => { try { vchart.removeSeries(vchart._v); } catch {} })();
    vchart._v = vchart.addHistogramSeries({ priceLineVisible: false });
    vchart._v.setData(data.map(x => ({ time: x.time, value: x.volume || 0, color: x.close >= x.open ? css("--up") : css("--down") })));
    chart.timeScale().fitContent(); vchart.timeScale().fitContent();
  }
  draw();
  chart.timeScale().subscribeVisibleLogicalRangeChange(r => { if (r) vchart.timeScale().setVisibleLogicalRange(r); });
  $("#ranges").onclick = e => { const b = e.target.closest("button"); if (!b) return; if (b.dataset.r) { state.range = b.dataset.r; $("#ranges").querySelectorAll("[data-r]").forEach(x => x.classList.toggle("on", x === b)); } if (b.dataset.type) { state.type = b.dataset.type; $("#ranges").querySelectorAll(".ctype").forEach(x => x.classList.toggle("on", x === b)); } draw(); };
  $("#inds").onclick = e => { const b = e.target.closest("button"); if (!b) return; const k = b.dataset.i; state.inds.has(k) ? state.inds.delete(k) : state.inds.add(k); b.classList.toggle("on"); draw(); };
}

// ---------- Stock detail page with interactive chart ----------
let chart = null, _chartRO = null;
async function openStock(sym) {
  const el = $("#detail");
  el.hidden = false; document.body.style.overflow = "hidden";
  el.innerHTML = `<div class="shead"><button onclick="closeStock()">←</button><b>${esc(sym)}</b><span class="muted" id="dsub"></span></div><div class="sbody"><p class="muted">Loading ${esc(sym)}…</p></div>`;
  let d;
  try { d = await (await fetch(`data/stocks/${sym}.json?` + Date.now())).json(); }
  catch { $(".sbody", el).innerHTML = `<div class="card warn">No detail for ${esc(sym)} yet — it may not be in the scored set. <a href="https://www.screener.in/company/${esc(sym)}/" target="_blank" rel="noopener">Open in Screener</a></div>`; return; }
  renderStock(el, d);
}
function closeStock() { const el = $("#detail"); el.hidden = true; document.body.style.overflow = ""; window._openSym = null; window._openDetail = null; if (chart) { try { chart.remove(); } catch {} chart = null; } }
window.addEventListener("popstate", () => { if (!$("#detail").hidden) closeStock(); });

function renderStock(el, d) {
  const T = d.trading, I = d.investing, R = d.reading, star = inWatch(d.symbol) ? "on" : "";
  window._openSym = d.symbol;
  window._openDetail = { symbol: d.symbol, name: d.name, price: d.price, trading_score: T.score, trading_verdict: T.verdict,
    buy_upto: T.buy_upto, stop: T.stop_loss, target_1: T.target_1, investing_score: I.score, investing_verdict: I.verdict,
    rsi: d.indicators && d.indicators.rsi, reading_summary: R.summary, support: R.support, resistance: R.resistance, fundamentals: d.fundamentals };
  $("#dsub", el).textContent = `₹${num(d.price)} · ${d.day_change >= 0 ? "+" : ""}${(d.day_change * 100).toFixed(2)}% · as of ${d.asof}`;
  const fund = d.fundamentals ? `<div class="card"><b>Fundamentals</b><div class="lvl" style="grid-template-columns:auto 1fr auto 1fr">
    <span>P/E</span><span>${num(d.fundamentals.pe, 1)}</span><span>ROE</span><span>${d.fundamentals.roe != null ? (d.fundamentals.roe * 100).toFixed(0) + "%" : "–"}</span>
    <span>Debt/Eq</span><span>${num(d.fundamentals.debt_equity, 0)}</span><span>Rev growth</span><span>${d.fundamentals.rev_growth != null ? (d.fundamentals.rev_growth * 100).toFixed(0) + "%" : "–"}</span>
    <span>Margin</span><span>${d.fundamentals.profit_margin != null ? (d.fundamentals.profit_margin * 100).toFixed(0) + "%" : "–"}</span><span>Div yld</span><span>${d.fundamentals.div_yield != null ? num(d.fundamentals.div_yield, 2) + "%" : "–"}</span></div></div>` : "";
  $(".sbody", el).innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
      <div><h2 style="margin:0">${esc(d.name)}</h2><span class="muted">${esc(d.symbol)} · ${d.days_history} days history · ${esc(d.source)}</span></div>
      <button class="star ${star}" id="star" title="Watchlist">${star ? "★" : "☆"}</button></div>

    <div class="grid" style="margin-top:10px">
      <div class="mode-card trade"><span class="mode-tag trade">Trading</span> <span class="muted">score ${T.score}</span>
        <div class="vd ${T.verdict_class}" style="margin:6px 0">${esc(T.verdict)}</div>
        <div class="lvl"><span>Good to buy up to</span><span>${T.buy_upto ? "₹" + num(T.buy_upto) : "—"}</span><span>Entry zone</span><span>₹${num(T.entry_low)}–${num(T.entry_high)}</span>
        <span>Stop-loss</span><span class="down">₹${num(T.stop_loss)}</span><span>Targets</span><span class="up">₹${num(T.target_1)} / ${num(T.target_2)}</span>
        <span>Risk:reward</span><span>${T.risk_reward || "–"} · time-stop ${T.time_stop_days}d</span></div>
        <div class="muted" style="font-size:12px;margin-top:6px">${esc(T.gap_rule)} ${esc(T.applies)}</div></div>
      <div class="mode-card invest"><span class="mode-tag invest">Investing</span> <span class="muted">score ${I.score}</span>
        <div class="vd ${I.verdict_class}" style="margin:6px 0">${esc(I.verdict)}</div>
        <div class="muted" style="font-size:13px">${esc(I.entry_style)}<br>${esc(I.thesis_broken_if)}<br>${esc(I.review)}</div></div>
    </div>

    <div class="chartbox">
      <div class="ranges" id="ranges">${["1M", "3M", "6M", "1Y", "3Y", "Max"].map(r => `<button data-r="${r}" class="${r === "6M" ? "on" : ""}">${r}</button>`).join("")}
        <span style="flex:1"></span><button data-type="candle" class="ctype on">Candles</button><button data-type="line" class="ctype">Line</button></div>
      <div class="inds" id="inds">${[["sma20", "SMA20"], ["sma50", "SMA50"], ["sma200", "SMA200"], ["bb", "Bollinger"], ["levels", "Entry/Stop/Target"]].map(([k, l]) => `<button data-i="${k}" class="${["sma50", "sma200", "levels"].includes(k) ? "on" : ""}">${l}</button>`).join("")}</div>
      <div class="chartwrap" id="chart"></div><div class="volwrap" id="vol"></div>
      <div class="muted" style="font-size:12px">End-of-day candles. Weekly/monthly views aggregate daily data. No intraday.</div>
    </div>

    <div class="card"><b>Chart reading</b> <span class="muted">(rule-based, as of ${d.asof})</span>
      <div class="reading-row"><span>Short</span><span>${esc(R.short)}</span></div>
      <div class="reading-row"><span>Medium</span><span>${esc(R.medium)}</span></div>
      <div class="reading-row"><span>Long</span><span>${esc(R.long)}</span></div>
      <div class="reading-row"><span>Momentum</span><span>${esc(R.momentum)}</span></div>
      <div class="reading-row"><span>Volume</span><span>${esc(R.volume)}</span></div>
      <div class="reading-row"><span>Volatility</span><span>${esc(R.volatility)}</span></div>
      <div class="reading-row"><span>Levels</span><span>Support ₹${num(R.support)} · Resistance ₹${num(R.resistance)}</span></div>
      ${R.events.length ? `<div style="margin:8px 0">${R.events.map(e => `<span class="evt">${esc(e)}</span>`).join("")}</div>` : ""}
      <p style="margin:8px 0 0"><b>${esc(R.summary)}</b><br><span class="muted">Watch next: ${esc(R.watch_next)}</span></p></div>

    <div class="card sizer"><b>Position size</b> <span class="muted">(saved on this device)</span>
      <div style="display:flex;gap:8px;margin-top:8px"><input id="cap" type="number" placeholder="Capital ₹" value="${LS.get("cap") || ""}"><input id="riskpct" type="number" placeholder="Risk % per trade" value="${LS.get("riskpct") || 1}"></div>
      <div class="out" id="sizeout"></div>
      <div class="muted" style="font-size:12px">Quantity so that (entry − stop) × qty ≈ your rupee risk. Buy at market up to the "good to buy" price.</div></div>

    ${fund}
    <div class="card"><b>Open in</b> · <a href="${esc(d.links.tickertape || "#")}" target="_blank" rel="noopener">Tickertape</a> · <a href="${esc(d.links.screener || "#")}" target="_blank" rel="noopener">Screener</a> · <a href="${esc(d.links.moneycontrol || "#")}" target="_blank" rel="noopener">Moneycontrol</a></div>
    <p class="muted" style="font-size:12px">${esc(d.disclaimer)}</p>`;

  // star
  $("#star", el).onclick = () => { toggleWatch(d.symbol); const on = inWatch(d.symbol); $("#star", el).classList.toggle("on", on); $("#star", el).textContent = on ? "★" : "☆"; };
  // position sizer
  const sizer = () => {
    const cap = parseFloat($("#cap", el).value) || 0, rp = parseFloat($("#riskpct", el).value) || 0;
    LS.set("cap", cap); LS.set("riskpct", rp);
    const perShare = T.entry_high - T.stop_loss;
    if (cap > 0 && rp > 0 && perShare > 0) {
      const risk = cap * rp / 100, qty = Math.floor(risk / perShare), cost = qty * T.entry_high;
      $("#sizeout", el).innerHTML = `Buy <b>${qty}</b> shares ≈ ₹${num(cost, 0)} · risking ₹${num(qty * perShare, 0)} if stopped`;
    } else $("#sizeout", el).textContent = "Enter capital and risk % above.";
  };
  $("#cap", el).oninput = sizer; $("#riskpct", el).oninput = sizer; sizer();
  // chart
  buildChart(d);
}

function search() {
  if (!UNI) return `<div class="card">The full stock list will appear after the next data update.</div>`;
  return `<h2>All NSE stocks <span class="muted" style="font-size:13px">(${UNI.total}, as of ${UNI.asof})</span></h2>
  <p class="muted">${UNI.eligible} pass the liquidity gate and are eligible for picks. The rest stay searchable but are labelled — thin or small stocks are riskier. Source: ${esc(UNI.source)} bhavcopy.</p>
  <input id="q" placeholder="Search ${UNI.total} stocks by name or symbol…" style="width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:9px;background:var(--card);color:var(--ink);font:inherit;margin-bottom:6px">
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
    <label class="muted" style="font-size:13px"><input type="checkbox" id="onlyElig"> Eligible only</label>
    <label class="muted" style="font-size:13px"><input type="checkbox" id="noSme" checked> Hide SME</label>
  </div>
  <div id="results"></div>`;
}
function wireSearch() {
  const q = $("#q"), res = $("#results"), onlyElig = $("#onlyElig"), noSme = $("#noSme");
  const render = () => {
    const term = (q.value || "").trim().toLowerCase();
    let rows = UNI.symbols;
    if (noSme.checked) rows = rows.filter(r => r.board !== "SME");
    if (onlyElig.checked) rows = rows.filter(r => r.eligible);
    if (term) rows = rows.filter(r => r.symbol.toLowerCase().includes(term) || (r.name || "").toLowerCase().includes(term));
    const show = rows.slice(0, 200);
    res.innerHTML = `<div class="muted" style="font-size:12px;margin-bottom:6px">${rows.length} match${rows.length === 1 ? "" : "es"}${rows.length > 200 ? " — showing first 200" : ""}</div>` +
      `<div class="scroll"><table><thead><tr><th>Symbol</th><th>Name</th><th class="n">Close ₹</th><th class="n">Day</th><th class="n">20d ₹cr</th><th>Status</th><th>Links</th></tr></thead><tbody>` +
      show.map(r => `<tr><td><b>${esc(r.symbol)}</b></td><td>${esc(r.name)}</td><td class="n">${r.close == null ? "–" : num(r.close)}</td>
        <td class="n">${pct(r.day_change)}</td><td class="n">${num(r.med_turnover_cr, 1)}</td>
        <td>${r.eligible ? '<span class="chip BUY">Eligible</span>' : `<span class="chip HOLD" title="${esc(r.reason)}">${esc(r.board === "SME" ? "SME" : "Not eligible")}</span>`}</td>
        <td style="font-size:12px"><a href="${esc(r.tickertape)}" target="_blank" rel="noopener">TT</a> · <a href="${esc(r.screener)}" target="_blank" rel="noopener">Scr</a> · <a href="${esc(r.moneycontrol)}" target="_blank" rel="noopener">MC</a></td></tr>`).join("") +
      `</tbody></table></div>`;
    if (!rows.length) res.innerHTML = `<div class="muted">No matches.</div>`;
  };
  q.oninput = render; onlyElig.onchange = render; noSme.onchange = render;
  render();
}

function backtest() {
  if (!BT) return `<h2>Backtest</h2><div class="card muted">The backtest runs weekly and appears once enough history has been collected.</div>`;
  const beats = BT.verdict && BT.verdict.includes("beats");
  const kpi = (l, v) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  return `<h2>Backtest of the Trading rule</h2>
    <div class="card ${beats ? "" : "warn"}"><b>${esc(BT.verdict || "Result")}</b>
      <div class="muted" style="font-size:13px;margin-top:4px">${esc(BT.method)}</div></div>
    <div class="kpis">
      ${kpi("Trades", BT.trades)}${kpi("Symbols", BT.symbols_tested)}${kpi("Win rate", Math.round(BT.win_rate * 100) + "%")}
      ${kpi("Expectancy / trade", BT.expectancy_pct + "%")}${kpi("Avg win", BT.avg_win_pct + "%")}${kpi("Avg loss", BT.avg_loss_pct + "%")}
      ${kpi("Profit factor", BT.profit_factor ?? "–")}${kpi("Rule total return", BT.total_return_pct + "%")}${kpi("Nifty 3y", BT.nifty_3y_return_pct != null ? BT.nifty_3y_return_pct + "%" : "–")}</div>
    <p class="muted">Costs assumed: ${BT.cost_assumption_pct}% round-trip (brokerage + slippage). "Rule total return" compounds trades sequentially (a simplification — real trades overlap across stocks), so read <b>expectancy per trade</b> and <b>win rate</b> as the honest headline. If the rule doesn't beat the index, the app says so — don't trust a signal the history doesn't support.</p>`;
}

function today() {
  const r = D.regime, col = r === "RISK-ON" ? "up" : r === "RISK-OFF" ? "down" : "";
  const nifty = D.indices.find(i => i.symbol === "^NSEI"), sensex = D.indices.find(i => i.symbol === "^BSESN");
  const q = i => i ? `<div><b>${esc(i.name)}</b> ${num(i.price)} ${pct(i.day_change)} <span class="muted">· ${esc(i.signal)}</span></div>` : "";
  const gold = D.commodities.find(c => c.symbol === "GC=F"), silver = D.commodities.find(c => c.symbol === "SI=F");
  const usd = D.currencies.find(c => c.symbol === "USDINR=X");
  const aiCard = BRIEF && BRIEF.brief ? `<div class="card ai-overview"><div class="tag">✨ AI overview</div><p style="margin:6px 0 0">${esc(BRIEF.brief)}</p><div class="muted" style="font-size:11px;margin-top:6px">Generated from today's computed data. Tap ✨ to ask follow-ups.</div></div>` : "";
  const tt = MODES && MODES.trading_top5 || [], it = MODES && MODES.investing_top5 || [];
  const shortlists = (tt.length || it.length) ? `
    <h2>⚡ Trading shortlist</h2><div class="muted" style="font-size:13px;margin:-6px 0 6px">Swing ideas — tap for chart, levels & reading.</div>
    ${tt.slice(0, 3).map(x => modeCard(x, "trading")).join("")}<p class="muted"><a href="#" onclick="go('trading');return false">See all trading →</a></p>
    <h2>◈ Investing shortlist</h2><div class="muted" style="font-size:13px;margin:-6px 0 6px">Long-term ideas — quality & valuation first.</div>
    ${it.slice(0, 3).map(x => modeCard(x, "investing")).join("")}<p class="muted"><a href="#" onclick="go('investing');return false">See all investing →</a></p>` : "";
  return `${aiCard}<div class="card"><div class="muted">Market regime</div><div class="regime ${col}">${r}</div>
    <div class="muted">${D.breadth_above_200dma != null ? Math.round(D.breadth_above_200dma * 100) + "% of the tracked Indian stocks above their 200-day average. " : ""}
    ${r === "RISK-OFF" ? "Be defensive: fewer new buys, smaller sizes." : r === "RISK-ON" ? "Trend and breadth support buying on dips." : "Mixed signals: be selective and stagger entries."}</div>
    <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px">${q(nifty)}${q(sensex)}${q(gold)}${q(silver)}${q(usd)}</div></div>
    ${shortlists}
    ${D.data_gaps.length ? `<p class="muted">Data gaps today: ${esc(D.data_gaps.join(", "))}</p>` : ""}`;
}

function table(id, cols, rows, detail) {
  const st = sortState[id];
  if (st) rows = [...rows].sort((a, b) => { const x = st.f(a), y = st.f(b); return (x == null) - (y == null) || (x > y ? 1 : x < y ? -1 : 0) * st.d; });
  return `<div class="scroll"><table data-id="${id}"><thead><tr>${cols.map((c, i) => `<th class="${c.n ? "n" : ""}" data-c="${i}">${c.h}</th>`).join("")}</tr></thead><tbody>
  ${rows.map((r, ri) => `<tr class="row" data-r="${ri}">${cols.map(c => `<td class="${c.n ? "n" : ""}">${c.f(r)}</td>`).join("")}</tr>${detail ? `<tr class="det" hidden><td colspan="${cols.length}">${detail(r)}</td></tr>` : ""}`).join("")}
  </tbody></table></div>`;
}
const tables = {};
function reg(id, cols, rows, detail) { tables[id] = { cols, rows, detail }; return table(id, cols, rows, detail); }
function wireTables() {
  document.querySelectorAll("table[data-id]").forEach(t => {
    const id = t.dataset.id;
    t.querySelector("thead").onclick = e => {
      const th = e.target.closest("th"); if (!th) return; const c = tables[id].cols[th.dataset.c]; if (!c.s) return;
      const cur = sortState[id]; sortState[id] = { f: c.s, d: cur && cur.c === c.s ? -cur.d : -1, c: c.s };
      t.closest(".scroll").outerHTML = table(id, tables[id].cols, tables[id].rows, tables[id].detail); wireTables();
    };
    t.querySelector("tbody").onclick = e => { const tr = e.target.closest("tr.row"); if (tr && tr.nextElementSibling?.classList.contains("det")) tr.nextElementSibling.hidden = !tr.nextElementSibling.hidden; };
  });
}
const planDetail = r => `<b>${esc(r.reason)}</b><br>Buy zone ${num(r.entry_low)}–${num(r.entry_high)} · Stop-loss ${num(r.stop_loss)} · Target 1 ${num(r.target_1)} · Target 2 ${num(r.target_2)}<br>
  <span class="muted">${esc(r.trail_rule)}. RSI ${num(r.rsi, 0)} · 50DMA ${num(r.sma50)} · 200DMA ${num(r.sma200)} · 52w-high distance ${pct(r.from_52w_high, 0)} · volatility ${num(r.vol_ann * 100, 0)}%</span>`
  + (r.fundamentals ? `<br><span class="muted">P/E ${num(r.fundamentals.pe, 1)} · ROE ${r.fundamentals.roe != null ? num(r.fundamentals.roe * 100, 0) + "%" : "–"} · Debt/Equity ${num(r.fundamentals.debt_equity, 0)} · Revenue growth ${r.fundamentals.rev_growth != null ? num(r.fundamentals.rev_growth * 100, 0) + "%" : "–"} · Dividend yield ${r.fundamentals.div_yield != null ? num(r.fundamentals.div_yield, 2) + "%" : "–"}</span>` : "");
const assetCols = (cur = "") => [
  { h: "Name", f: r => esc(r.name), s: r => r.name }, { h: "Price", n: 1, f: r => cur + num(r.price), s: r => r.price },
  { h: "Day", n: 1, f: r => pct(r.day_change), s: r => r.day_change }, { h: "1M", n: 1, f: r => pct(r.ret_1m, 0), s: r => r.ret_1m },
  { h: "3M", n: 1, f: r => pct(r.ret_3m, 0), s: r => r.ret_3m }, { h: "1Y", n: 1, f: r => pct(r.ret_1y, 0), s: r => r.ret_1y },
  { h: "RSI", n: 1, f: r => num(r.rsi, 0), s: r => r.rsi }, { h: "Score", f: r => bar(r.score), s: r => r.score }, { h: "Signal", f: r => chip(r.signal), s: r => r.signal }];
const stocks = () => `<h2>Nifty-50 stocks, ranked</h2><p class="muted">Click a row for buy zone, stop, targets and fundamentals. Click a column header to sort. Score = trend + momentum (70) + fundamentals (30).</p>
  ${reg("stocks", [...assetCols("₹"), { h: "Sector", f: r => esc(r.sector || "–"), s: r => r.sector }], D.stocks, planDetail)}`;
const metals = () => `<h2>Gold, silver, metals & energy</h2><p class="muted">Global futures prices in US dollars. Indian prices also depend on USD/INR and import duty. Rare-earth rows are listed proxies (ETF / miner), as there is no free spot feed.</p>
  ${reg("metals", [...assetCols("$"), { h: "Type", f: r => esc(r.kind), s: r => r.kind }], D.commodities, planDetail)}`;
const global = () => `<h2>India</h2>${reg("gi", assetCols(), D.indices.filter(i => i.region === "India"), planDetail)}
  <h2>US, UK, Japan, China & others</h2>${reg("gg", [...assetCols(), { h: "Region", f: r => esc(r.region), s: r => r.region }], D.indices.filter(i => i.region !== "India"), planDetail)}`;
const funds = () => `<h2>Mutual funds (Direct, Growth)</h2><p class="muted">Ranked on 3-year CAGR, return per unit of volatility, and worst drawdown. Check expense ratio, fund manager and your goal before investing; for equity funds prefer a monthly SIP over a lump sum.</p>
  ${reg("funds", [{ h: "Fund", f: r => esc(r.name), s: r => r.name }, { h: "Category", f: r => esc(r.category.replace(/^Equity Scheme - /, "")), s: r => r.category },
  { h: "NAV", n: 1, f: r => num(r.nav), s: r => r.nav }, { h: "1Y", n: 1, f: r => pct(r.ret_1y, 0), s: r => r.ret_1y }, { h: "3Y CAGR", n: 1, f: r => pct(r.cagr_3y, 1), s: r => r.cagr_3y },
  { h: "5Y CAGR", n: 1, f: r => pct(r.cagr_5y, 1), s: r => r.cagr_5y }, { h: "Max drawdown", n: 1, f: r => pct(r.max_drawdown, 0), s: r => r.max_drawdown }, { h: "Score", f: r => bar(r.score), s: r => r.score }], D.mutual_funds)}`;
const fx = () => `<h2>Currencies vs INR</h2><p class="muted">Price = rupees per 1 unit. A rising number means the rupee is weakening (good for exporters / foreign holdings, bad for importers & overseas travel).</p>
  ${reg("fx", [{ h: "Currency", f: r => esc(r.name), s: r => r.name }, { h: "Rate", n: 1, f: r => num(r.price, 3), s: r => r.price }, { h: "1M", n: 1, f: r => pct(r.ret_1m), s: r => r.ret_1m }, { h: "3M", n: 1, f: r => pct(r.ret_3m), s: r => r.ret_3m },
  { h: "1Y", n: 1, f: r => pct(r.ret_1y), s: r => r.ret_1y }, { h: "View", f: r => esc(r.inr_view || "Dollar strength gauge"), s: r => r.name }], D.currencies)}
  <h2>Bond yields</h2><p class="muted">Rising yields = falling bond prices. Indian 10-year G-Sec data is not on a free feed; track it on RBI / CCIL.</p>
  ${reg("y", [{ h: "Instrument", f: r => esc(r.name) }, { h: "Yield %", n: 1, f: r => num(r.value, 2) }, { h: "1M change", n: 1, f: r => num(r.chg_1m, 2) + " pts" }, { h: "3M change", n: 1, f: r => num(r.chg_3m, 2) + " pts" }], D.yields)}`;
const ipo = () => D.ipos.ok ? `<h2>IPOs</h2><p class="muted">Source: ${esc(D.ipos.source)} (unofficial). Always confirm dates, price band and GMP risk on NSE/BSE before applying; subscribe only after reading the RHP.</p>
  ${reg("ipo", Object.keys(D.ipos.rows[0] || {}).map(k => ({ h: esc(k), f: r => esc(r[k]) })), D.ipos.rows)}`
  : `<h2>IPOs</h2><div class="card warn">Automatic IPO scraping failed today (${esc(D.ipos.error || "")}). Free IPO sources are unofficial. Check directly:<ul>${(D.ipos.manual_links || []).map(l => `<li><a href="${esc(l)}" target="_blank" rel="noopener">${esc(l)}</a></li>`).join("")}</ul></div>
  <p class="muted">IPO checklist: profitability and debt, use of proceeds (fresh issue vs offer-for-sale), valuation vs listed peers, anchor investors, subscription level on day 3.</p>`;
const track = () => { const s = TR.summary || {}; return `<h2>Track record of past top picks</h2><p class="muted">Every stock/commodity pick is logged with its entry, stop and Target 1 and marked to market daily. This shows whether the rules actually work, so judge it before trusting the signals.</p>
  <div class="card">Logged: ${s.total ?? 0} · Open: ${s.open ?? 0} · Target-hit rate on closed picks: ${s.hit_rate != null ? Math.round(s.hit_rate * 100) + "%" : "n/a yet"}</div>
  ${reg("tr", [{ h: "Date", f: r => r.date, s: r => r.date }, { h: "Pick", f: r => esc(r.name) }, { h: "Entry", n: 1, f: r => num(r.entry) }, { h: "Stop", n: 1, f: r => num(r.stop) }, { h: "Target 1", n: 1, f: r => num(r.target) },
  { h: "Now", n: 1, f: r => num(r.last) }, { h: "P&L", n: 1, f: r => pct((r.pnl_pct || 0) / 100), s: r => r.pnl_pct }, { h: "Status", f: r => chip(r.status === "TARGET HIT" ? "BUY target hit" : r.status === "STOPPED" ? "SELL stopped" : "HOLD open") }], [...(TR.picks || [])].reverse())}`; };
const news = () => `<h2>Headlines</h2>` + Object.entries(D.news).map(([k, v]) => `<div class="card"><b>${esc(k)}</b><ul>${v.map(n => `<li><a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a></li>`).join("") || "<li class='muted'>unavailable</li>"}</ul></div>`).join("");
const how = () => `<h2>How the picks are made</h2><div class="card"><ul>
  <li><b>Score (0–100)</b>: trend (price vs 50 & 200-day averages) 30 + momentum (3m & 6m returns) 25 + RSI sanity 10 + distance to 52-week high 5 + fundamentals 30 (P/E, ROE, debt, growth, margin from Yahoo). Missing fundamentals count as neutral.</li>
  <li><b>BUY</b> = uptrend and score ≥ 62 and not overbought. <b>SELL/AVOID</b> = below both averages. <b>Levels</b> come from ATR volatility, giving about a 1.5:1 reward-to-risk to Target 1.</li>
  <li><b>When to sell</b>: stop-loss hit, price closes below the stop/50-day after Target 1, or the signal flips to SELL. For mutual funds, use SIPs and review yearly; don't trade them.</li>
  <li><b>Market regime</b> turns RISK-OFF when Nifty is below its averages and under 40% of tracked stocks are above their 200-day average; buys are then suppressed.</li></ul>
  <p class="muted">Limitations: end-of-day delayed data; not all of the Nifty-50 have clean fundamentals on free feeds; the rules are generic and untested on your goals; taxes (STCG/LTCG), brokerage and slippage are ignored. This is a research aid, not advice from a SEBI-registered adviser.</p></div>`;

if (location.hash.slice(1) && TABS.some(t => t[0] === location.hash.slice(1))) tab = location.hash.slice(1);
load();

// ================= In-app AI assistant (uses YOUR Anthropic key, stored on this device only) =================
// Free, open-source-friendly AI providers (no card needed). Default = OpenRouter free Llama.
const AI_PROVIDERS = {
  openrouter: { label: "OpenRouter (free, open-source)", url: "https://openrouter.ai/api/v1/chat/completions", kind: "openai",
    model: "meta-llama/llama-3.3-70b-instruct:free", keyUrl: "openrouter.ai/keys", keyHint: "or_... (free, no card)" },
  groq: { label: "Groq (free, fast, Llama)", url: "https://api.groq.com/openai/v1/chat/completions", kind: "openai",
    model: "llama-3.3-70b-versatile", keyUrl: "console.groq.com/keys", keyHint: "gsk_... (free, no card)" },
  gemini: { label: "Google Gemini (free)", url: "https://generativelanguage.googleapis.com/v1beta/models", kind: "gemini",
    model: "gemini-flash-latest", keyUrl: "aistudio.google.com/apikey", keyHint: "AIza... (free, no card)" },
  anthropic: { label: "Anthropic Claude (paid)", url: "https://api.anthropic.com/v1/messages", kind: "anthropic",
    model: "claude-sonnet-5-5", keyUrl: "console.anthropic.com", keyHint: "sk-ant-... (needs payment)" },
};
const AI = {
  provider: () => LS.get("ai_provider") || "openrouter",
  cfg: () => AI_PROVIDERS[AI.provider()] || AI_PROVIDERS.openrouter,
  key: () => LS.get("ai_key_" + (LS.get("ai_provider") || "openrouter")),
  model: () => LS.get("ai_model_" + (LS.get("ai_provider") || "openrouter")) || AI.cfg().model,
  history: [],
};
const TUTOR = `You are the built-in assistant inside a personal Indian stock-market dashboard called Market Tracker, used by one retail investor.
Your jobs: (1) explain what the user is looking at and how to use the app's workflow; (2) teach stock-market concepts from basics to advanced (e.g. candlesticks, moving averages, RSI, MACD, valuation, P/E, ROE, position sizing, risk management, portfolio theory, market regimes, options basics) in plain language with small examples; (3) interpret the COMPUTED data you are given.
Hard rules: use ONLY the numbers provided in context — never invent prices, levels or percentages; if you don't have a number, say so. Be concise and friendly. Never promise returns or give a guaranteed call. For anything actionable, remind that this is a research aid, not SEBI-registered advice, and to verify independently. Prefer short paragraphs and bullet points.`;

function aiContext() {
  const c = { tab, regime: D && D.regime, breadth: D && D.breadth_above_200dma };
  if (!$("#detail").hidden && window._openSym) c.open_stock = window._openSym;
  if (tab === "today" && BRIEF) c.ai_brief = BRIEF.brief;
  if ((tab === "trading" || tab === "investing") && MODES) {
    const key = tab === "trading" ? "trading_top5" : "investing_top5";
    c[key] = (MODES[key] || []).map(r => ({ symbol: r.symbol, name: r.name, trading_score: r.trading_score, investing_score: r.investing_score, verdict: r.trading_verdict_txt || r.investing_verdict_txt }));
  }
  if (tab === "backtest" && BT) c.backtest = { win_rate: BT.win_rate, expectancy_pct: BT.expectancy_pct, verdict: BT.verdict };
  if (window._openDetail) c.stock_detail = window._openDetail;
  return c;
}
const QUICK = {
  today: ["Explain today's market in simple words", "What should a beginner look at first?"],
  trading: ["How do I use this trading shortlist?", "What is a stop-loss and position size?"],
  investing: ["How is investing different from trading here?", "What makes a good long-term stock?"],
  backtest: ["Is this strategy good? Explain the numbers", "What is expectancy and win rate?"],
  _default: ["Explain this screen", "Teach me a stock-market basic", "What is RSI?"],
};
function _aiEsc(ev) { if (ev.key === "Escape") aiClose(); }
function aiClose() {
  $("#aipanel").hidden = true;
  document.body.classList.remove("ai-open");
  const b = document.getElementById("aiback"); if (b) b.remove();
  document.removeEventListener("keydown", _aiEsc);
}
function aiToggle() { $("#aipanel").hidden ? aiOpen() : aiClose(); }
function aiOpen() {
  if (!document.getElementById("aiback")) {
    const b = document.createElement("div"); b.id = "aiback"; b.className = "aiback"; b.onclick = aiClose;
    document.body.appendChild(b);
  }
  document.body.classList.add("ai-open");
  document.addEventListener("keydown", _aiEsc);
  aiRender();
}
function aiRender() {
  const p = $("#aipanel"); p.hidden = false;
  const closeBtns = `<button class="x" title="Close" onclick="aiClose()">×</button>`;
  if (!AI.key()) {
    const prov = AI.provider(), cfg = AI.cfg();
    p.innerHTML = `<div class="ahead"><b>✨ Ask AI</b>${closeBtns}</div>
      <div class="aimsgs"><div class="amsg a">Hi! I explain any screen, teach stock-market concepts (basic to advanced), and interpret the app's numbers.
      <br><br>Pick a <b>free</b> AI provider and paste its key (no card needed). It's stored only on this device and never uploaded.</div>
      <div class="amsg a">Recommended: <b>OpenRouter</b> or <b>Groq</b> — free, open-source Llama models. Get a free key at <b>${esc(cfg.keyUrl)}</b>.</div></div>
      <div style="padding:0 14px 8px"><select id="aiprov" onchange="aiPickProvider(this.value)" style="width:100%;padding:9px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--ink);font:inherit">
        ${Object.entries(AI_PROVIDERS).map(([k, v]) => `<option value="${k}" ${k === prov ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></div>
      <div class="ainput"><input id="aikey" type="password" placeholder="${esc(cfg.keyHint)}"><button onclick="aiSaveKey()">Save</button></div>
      <div style="text-align:center;padding:0 0 12px"><button style="background:var(--chip);color:var(--muted);border:1px solid var(--line);border-radius:8px;padding:8px 16px;font:inherit;cursor:pointer" onclick="aiClose()">Maybe later</button></div>`;
    return;
  }
  const chips = (QUICK[tab] || QUICK._default);
  p.innerHTML = `<div class="ahead"><b>✨ Ask AI</b><span style="flex:1"></span><button class="x" title="Settings" onclick="aiSettings()">⚙</button>${closeBtns}</div>
    <div class="aimsgs" id="aimsgs">${AI.history.length ? "" : `<div class="amsg a">Ask me about the <b>${esc(tab)}</b> screen, or any market concept.</div>`}
    ${AI.history.map(m => `<div class="amsg ${m.role === "user" ? "u" : "a"}">${esc(m.text)}</div>`).join("")}</div>
    <div class="chips">${chips.map(q => `<button onclick="aiSend(this.textContent)">${esc(q)}</button>`).join("")}</div>
    <div class="ainput"><input id="aiq" placeholder="Ask anything…" onkeydown="if(event.key==='Enter'){aiSend(this.value);this.value=''}"><button onclick="var i=document.getElementById('aiq');aiSend(i.value);i.value=''">Send</button></div>`;
  const m = $("#aimsgs"); m.scrollTop = m.scrollHeight;
}
function aiPickProvider(p) { LS.set("ai_provider", p); aiRender(); }
function aiSaveKey() { const k = $("#aikey").value.trim(); if (k) { LS.set("ai_key_" + AI.provider(), k); aiRender(); } }
function aiSettings() {
  const m = prompt("Model for " + AI.cfg().label + " (blank = default " + AI.cfg().model + "):", AI.model());
  if (m !== null) { if (m.trim()) LS.set("ai_model_" + AI.provider(), m.trim()); else localStorage.removeItem("ai_model_" + AI.provider()); }
  if (confirm("Also clear your saved API key from this device?")) { localStorage.removeItem("ai_key_" + AI.provider()); AI.history = []; }
  aiRender();
}
async function aiCall(messages, sys) {
  const cfg = AI.cfg(), key = AI.key(), model = AI.model();
  if (cfg.kind === "anthropic") {
    const r = await fetch(cfg.url, { method: "POST", headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" },
      body: JSON.stringify({ model, max_tokens: 900, system: sys, messages }) });
    const j = await r.json(); if (!r.ok) throw new Error((j.error && j.error.message) || "error " + r.status);
    return j.content[0].text;
  }
  if (cfg.kind === "gemini") {
    const url = `${cfg.url}/${model}:generateContent?key=${encodeURIComponent(key)}`;
    const contents = messages.map(m => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] }));
    const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ system_instruction: { parts: [{ text: sys }] }, contents, generationConfig: { maxOutputTokens: 900 } }) });
    const j = await r.json(); if (!r.ok) throw new Error((j.error && j.error.message) || "error " + r.status);
    return j.candidates[0].content.parts.map(p => p.text).join("");
  }
  // openai-compatible (OpenRouter, Groq)
  const r = await fetch(cfg.url, { method: "POST", headers: { "content-type": "application/json", "authorization": "Bearer " + key, "HTTP-Referer": location.origin, "X-Title": "Market Tracker" },
    body: JSON.stringify({ model, max_tokens: 900, messages: [{ role: "system", content: sys }, ...messages] }) });
  const j = await r.json(); if (!r.ok) throw new Error((j.error && (j.error.message || j.error)) || "error " + r.status);
  return j.choices[0].message.content;
}
async function aiSend(text) {
  text = (text || "").trim(); if (!text || !AI.key()) return;
  AI.history.push({ role: "user", text }); aiRender();
  const msgs = $("#aimsgs"); const bubble = document.createElement("div"); bubble.className = "amsg a"; bubble.textContent = "…"; msgs.appendChild(bubble); msgs.scrollTop = msgs.scrollHeight;
  try {
    const sys = TUTOR + "\n\nCONTEXT (computed app data for the user's current screen):\n" + JSON.stringify(aiContext());
    const msgsArr = AI.history.map(m => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
    const txt = await aiCall(msgsArr, sys);
    AI.history.push({ role: "assistant", text: txt || "(no reply)" });
  } catch (e) {
    AI.history.push({ role: "assistant", text: "⚠ " + e.message + (/401|403|auth|invalid/i.test(e.message) ? " — check your key/provider in ⚙." : "") });
  }
  aiRender();
}
$("#aifab").onclick = aiToggle;

// ---- PWA: install prompt + service worker ----
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
let deferredPrompt = null;
const installBtn = $("#install");
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferredPrompt = e; if (installBtn) installBtn.hidden = false; });
if (installBtn) installBtn.onclick = async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt(); await deferredPrompt.userChoice; deferredPrompt = null; installBtn.hidden = true;
};
window.addEventListener("appinstalled", () => { if (installBtn) installBtn.hidden = true; });

// ---- Web push: the installed app shows notifications itself ----
const VAPID_PUBLIC = "BBDbejKiTatsQvtGne7DepLU-mJnTHrOI3zQhIMivYb8Zh2fAN1aFOrqPhcAZCxSOeZSkMq5Y1RNktGTAPqN8Jo";
const b64ToU8 = s => { const p = "=".repeat((4 - s.length % 4) % 4); const b = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from([...b].map(c => c.charCodeAt(0))); };
const alertsBtn = $("#alerts");
function showSubModal(json) {
  const m = document.createElement("div"); m.className = "modal";
  m.innerHTML = `<div class="box"><b>Last step — paste this code into GitHub</b>
    <p class="muted" style="font-size:13px">Copy the text below, then in GitHub add a secret named <code>PUSH_SUBS</code> with this as its value. After that, this app shows your daily alerts itself.</p>
    <textarea readonly id="subtext">${esc(json)}</textarea>
    <div><button class="ok" id="copySub">Copy</button><button class="sec" id="closeSub">Close</button></div></div>`;
  document.body.appendChild(m);
  $("#copySub", m).onclick = () => { navigator.clipboard.writeText(json).then(() => $("#copySub", m).textContent = "Copied ✓"); };
  $("#closeSub", m).onclick = () => m.remove();
  m.onclick = e => { if (e.target === m) m.remove(); };
}
async function enableAlerts() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    alert("Your browser doesn't support app notifications. Open the site in Chrome and install the app first."); return;
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") { alert("Notifications are blocked. Enable them for this app in your phone settings, then try again."); return; }
  const reg = await navigator.serviceWorker.ready;
  // Always re-subscribe fresh: an old subscription may be tied to a stale key and the push server would reject it.
  const old = await reg.pushManager.getSubscription();
  if (old) { try { await old.unsubscribe(); } catch {} }
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(VAPID_PUBLIC) });
  reg.showNotification("Alerts are on ✓", { body: "Your daily Top 5 will appear here.", icon: "icon-192.png" });
  showSubModal(JSON.stringify(sub));
  alertsBtn.textContent = "Alerts on ✓"; alertsBtn.classList.add("done");
}
if (alertsBtn) {
  if (window.Notification && Notification.permission === "granted") { alertsBtn.textContent = "Alerts on ✓"; alertsBtn.classList.add("done"); }
  alertsBtn.onclick = enableAlerts;
}
