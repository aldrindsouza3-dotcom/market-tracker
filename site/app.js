"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1) => x == null ? "–" : `<span class="${x >= 0 ? "up" : "down"}">${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%</span>`;
const num = (x, d = 2) => x == null ? "–" : Number(x).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const cls = s => /^BUY|ACCUM|SIP/.test(s) ? "BUY" : /SELL/.test(s) ? "SELL" : "HOLD";
const chip = s => `<span class="chip ${cls(s)}">${esc(s)}</span>`;
const bar = v => `<span class="bar-s" style="width:${Math.max(2, v * 0.6)}px"></span>${v.toFixed(0)}`;
let D = null, TR = null, HIST = [], tab = "today";
const sortState = {};

const TABS = [["today", "Today"], ["overview", "Overview"], ["stocks", "India stocks"], ["funds", "Mutual funds"], ["metals", "Gold, silver & commodities"],
["fx", "Currency & bonds"], ["global", "Global markets"], ["ipo", "IPOs"], ["track", "Track record"], ["news", "News"], ["how", "How it works"]];

async function load() {
  try {
    const t = Date.now();
    D = await (await fetch("data/latest.json?" + t)).json();
    try { TR = await (await fetch("data/track_record.json?" + t)).json(); } catch { TR = { picks: [], summary: {} }; }
    try { HIST = await (await fetch("data/history.json?" + t)).json(); } catch { HIST = []; }
  } catch (e) {
    $("#view").innerHTML = `<div class="card warn">No data yet. Run <code>python pipeline/run_daily.py</code> once, then reload.</div>`; return;
  }
  const g = new Date(D.generated_at);
  $("#stamp").textContent = "Updated " + g.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) + " · end-of-day data";
  $("#foot").innerHTML = esc(D.disclaimer) + " Data: Yahoo Finance, AMFI via mfapi.in. May be delayed or incomplete.";
  $("#tabs").innerHTML = TABS.map(([k, l]) => `<button data-t="${k}" class="${k === tab ? "on" : ""}">${l}</button>`).join("");
  $("#tabs").onclick = e => { const b = e.target.closest("button"); if (b) { tab = b.dataset.t; history.replaceState(null, "", "#" + tab); load2(); } };
  load2();
}
function load2() {
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === tab));
  $("#view").innerHTML = ({ today, overview, stocks, funds, metals, fx, global, ipo, track, news, how }[tab])();
  wireTables();
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

function today() {
  const r = D.regime, col = r === "RISK-ON" ? "up" : r === "RISK-OFF" ? "down" : "";
  const nifty = D.indices.find(i => i.symbol === "^NSEI"), sensex = D.indices.find(i => i.symbol === "^BSESN");
  const q = i => i ? `<div><b>${esc(i.name)}</b> ${num(i.price)} ${pct(i.day_change)} <span class="muted">· ${esc(i.signal)}</span></div>` : "";
  const gold = D.commodities.find(c => c.symbol === "GC=F"), silver = D.commodities.find(c => c.symbol === "SI=F");
  const usd = D.currencies.find(c => c.symbol === "USDINR=X");
  return `<div class="card"><div class="muted">Market regime</div><div class="regime ${col}">${r}</div>
    <div class="muted">${D.breadth_above_200dma != null ? Math.round(D.breadth_above_200dma * 100) + "% of the tracked Indian stocks (Nifty-50 + 40 midcaps) above their 200-day average. " : ""}
    ${r === "RISK-OFF" ? "Be defensive: fewer new buys, smaller sizes." : r === "RISK-ON" ? "Trend and breadth support buying on dips." : "Mixed signals: be selective and stagger entries."}</div>
    <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px">${q(nifty)}${q(sensex)}${q(gold)}${q(silver)}${q(usd)}</div></div>
    <h2>Today's top 5</h2><div class="grid">${D.top5.map((p, i) => pickCard(p, i + 1)).join("")}</div>
    <p class="muted">Levels use volatility (ATR): stop = 2×ATR below, targets = 3× and 5×ATR above. Check the "How it works" tab and apply your own position sizing (risk ≤1–2% of capital per idea).</p>
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
