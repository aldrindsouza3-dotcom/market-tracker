"""Daily job: fetch -> score -> write site/data/latest.json -> log picks -> notify.

Usage:  python pipeline/run_daily.py [--no-notify] [--fast]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import analysis as A  # noqa: E402
import data as D  # noqa: E402
import notify as N  # noqa: E402
import universe as U  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
SITE_URL = os.environ.get("SITE_URL", "")
DISCLAIMER = "Rule-based research aid, not investment advice. Past performance does not guarantee future results."


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def analyse_asset(sym, name, df, fund=None, extra=None):
    t = A.technicals(df)
    if not t:
        return None
    ts = A.technical_score(t)
    fs, had = A.fundamental_score(fund) if fund is not None else (None, False)
    score = round(ts / 70 * 100 if fs is None else ts + fs, 1)
    row = {"symbol": sym, "name": name, "score": score, "tech_score": round(ts, 1),
           "fund_score": None if fs is None else round(fs, 1), "has_fundamentals": had,
           "day_change": t["price"] / t["prev_close"] - 1, **t, **A.trade_plan(t, score)}
    if fund:
        row["fundamentals"] = fund
    if extra:
        row.update(extra)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--fast", action="store_true", help="skip fundamentals and mutual funds (testing)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    gaps = []

    print("Fetching prices...")
    stock_syms = {f"{k}.NS": v for k, v in {**U.NIFTY50, **U.MIDCAPS}.items()}
    all_syms = list(stock_syms) + list(U.INDICES) + list(U.COMMODITIES) + list(U.RARE_EARTH_PROXIES) \
        + list(U.CURRENCIES) + list(U.YIELDS)
    px = D.prices(all_syms)
    gaps += [s for s in all_syms if s not in px]

    print("Scoring Indian stocks...")
    stocks = []
    for sym, name in stock_syms.items():
        if sym not in px:
            continue
        fund = None if args.fast else D.fundamentals(sym)
        r = analyse_asset(sym, name, px[sym], fund if not args.fast else {})
        if r:
            r["sector"] = (fund or {}).get("sector")
            stocks.append(r)
    stocks.sort(key=lambda r: -r["score"])

    indices = []
    for sym, (name, region) in U.INDICES.items():
        if sym in px:
            r = analyse_asset(sym, name, px[sym], extra={"region": region})
            if r:
                indices.append(r)
    indices.sort(key=lambda r: (r["region"] != "India", -r["score"]))

    commodities = []
    for group, label in ((U.COMMODITIES, "Commodity"), (U.RARE_EARTH_PROXIES, "Rare-earth proxy")):
        for sym, name in group.items():
            if sym in px:
                r = analyse_asset(sym, name, px[sym], extra={"kind": label})
                if r:
                    commodities.append(r)
    commodities.sort(key=lambda r: -r["score"])

    currencies = []
    for sym, name in U.CURRENCIES.items():
        if sym in px:
            r = analyse_asset(sym, name, px[sym])
            if r:
                # For INR pairs a rising price = INR weakening. Say so plainly.
                if sym.endswith("INR=X"):
                    r["inr_view"] = "INR weakening vs " + name if r["ret_3m"] > 0.01 else \
                        "INR strengthening vs " + name if r["ret_3m"] < -0.01 else "INR stable vs " + name
                currencies.append(r)

    yields = []
    for sym, name in U.YIELDS.items():
        if sym in px:
            c = px[sym]["Close"].dropna()
            yields.append({"symbol": sym, "name": name, "value": float(c.iloc[-1]),
                           "chg_1m": float(c.iloc[-1] - c.iloc[-22]) if len(c) > 22 else None,
                           "chg_3m": float(c.iloc[-1] - c.iloc[-64]) if len(c) > 64 else None})

    funds = []
    if not args.fast:
        print("Scoring mutual funds...")
        for q in U.MUTUAL_FUNDS:
            res = D.mf_nav_history(q)
            if not res:
                gaps.append(f"MF:{q}")
                continue
            meta, nav = res
            m = A.mf_metrics(nav)
            if m:
                funds.append({**meta, **m, "score": A.mf_score(m)})
        funds.sort(key=lambda r: -r["score"])

    print("IPOs / news...")
    ipos = D.upcoming_ipos()
    news = {"India markets": D.headlines("Nifty Sensex stock market India"),
            "Gold & silver": D.headlines("gold silver price India"),
            "Global": D.headlines("global markets Wall Street Asia stocks")}

    # Market regime from Nifty trend + breadth of the Nifty-50 list
    nifty = next((i for i in indices if i["symbol"] == "^NSEI"), None)
    above200 = sum(1 for s in stocks if not _nan(s["sma200"]) and s["price"] > s["sma200"])
    breadth = above200 / len(stocks) if stocks else None
    regime = "UNKNOWN"
    if nifty and breadth is not None:
        up = nifty["price"] > nifty["sma50"] and nifty["price"] > nifty["sma200"]
        regime = "RISK-ON" if up and breadth > 0.6 else "RISK-OFF" if (not up) and breadth < 0.4 else "MIXED"

    # Daily Top 5: best BUY signals across stocks, gold/silver, funds (kept diversified: max 3 stocks)
    cand = [dict(kind="Stock", **r) for r in stocks if r["signal"] == "BUY"][:3]
    cand += [dict(kind="Commodity", **r) for r in commodities if r["signal"] == "BUY"
             and r["symbol"] in ("GC=F", "SI=F", "HG=F")][:2]
    cand += [dict(kind="Mutual fund", symbol=str(f["code"]), name=f["name"], score=f["score"], signal="SIP / ACCUMULATE",
                  price=f["nav"], reason=f"3Y CAGR {((f['cagr_3y'] or f['ret_1y'] or 0) * 100):.1f}%, "
                  f"max drawdown {f['max_drawdown'] * 100:.0f}%") for f in _distinct_category(funds)[:2]]
    if regime == "RISK-OFF":
        cand = [c for c in cand if c["kind"] != "Stock"] or cand
    top5 = sorted(cand, key=lambda r: -r["score"])[:5]
    if len(top5) < 5:  # backfill with best-scoring non-sell stocks
        extra = [dict(kind="Stock", **r) for r in stocks if not r["signal"].startswith("SELL")
                 and all(r["symbol"] != t["symbol"] for t in top5)]
        top5 += extra[:5 - len(top5)]

    # Overview / analytics block, all derived from today's data (no history needed).
    adv = sum(1 for s in stocks if s["day_change"] > 0)
    dec = sum(1 for s in stocks if s["day_change"] < 0)
    sec = {}
    for s in stocks:
        k = s.get("sector") or "Unknown"
        sec.setdefault(k, []).append(s)
    sectors = sorted(({"sector": k, "count": len(v),
                       "avg_day": sum(x["day_change"] for x in v) / len(v),
                       "avg_score": round(sum(x["score"] for x in v) / len(v), 1),
                       "avg_3m": sum((x["ret_3m"] or 0) for x in v) / len(v)}
                      for k, v in sec.items() if k != "Unknown"), key=lambda r: -r["avg_day"])
    movers = sorted(stocks, key=lambda r: -(r["day_change"] or 0))
    snap = lambda sym, lst: next(({"name": x["name"], "price": x["price"], "day": x["day_change"],
                                   "ret_1m": x["ret_1m"], "signal": x.get("signal")}
                                  for x in lst if x["symbol"] == sym), None)
    overview = {
        "advancers": adv, "decliners": dec, "unchanged": len(stocks) - adv - dec,
        "buy_signals": sum(1 for s in stocks if s["signal"] == "BUY"),
        "sell_signals": sum(1 for s in stocks if s["signal"].startswith("SELL")),
        "sectors": sectors,
        "top_gainers": [{"name": m["name"], "day": m["day_change"], "signal": m["signal"]} for m in movers[:5]],
        "top_losers": [{"name": m["name"], "day": m["day_change"], "signal": m["signal"]} for m in movers[-5:][::-1]],
        "snapshot": {"Nifty 50": snap("^NSEI", indices), "Sensex": snap("^BSESN", indices),
                     "Bank Nifty": snap("^NSEBANK", indices), "S&P 500": snap("^GSPC", indices),
                     "Nikkei": snap("^N225", indices), "Gold": snap("GC=F", commodities),
                     "Silver": snap("SI=F", commodities), "USD/INR": snap("USDINR=X", currencies)},
    }

    out = {"generated_at": now.isoformat(), "asof_note": "End-of-day data (Yahoo Finance, delayed). Prices in local currency; INR for India.",
           "regime": regime, "breadth_above_200dma": breadth, "overview": overview, "top5": top5, "stocks": stocks, "indices": indices,
           "commodities": commodities, "currencies": currencies, "yields": yields, "mutual_funds": funds,
           "ipos": ipos, "news": news, "data_gaps": gaps, "disclaimer": DISCLAIMER}
    (OUT / "latest.json").write_text(json.dumps(clean(out), indent=1), encoding="utf-8")

    build_full_universe(now)  # whole-market searchable index + liquidity gate (safe, isolated)
    modes = None
    try:
        import build_stocks
        modes = build_stocks.build(now)   # dual Trading/Investing scoring + per-symbol detail + chart reading
    except Exception as _ex:
        print("  ! dual-mode build skipped:", str(_ex)[:140])
    try:
        import build_us
        build_us.build(now)       # US & global large caps + ETFs, scored via Yahoo
    except Exception as _ex:
        print("  ! US build skipped:", str(_ex)[:140])
    try:
        import backtest
        backtest.run(now)         # weekly-cached backtest of the Trading rule vs Nifty
    except Exception as _ex:
        print("  ! backtest skipped:", str(_ex)[:140])
    append_history(now, regime, breadth, nifty, indices, commodities, currencies, adv, dec)
    update_track_record(now, top5, px)

    # AI market brief + why-selected rationale (optional; only if ANTHROPIC_API_KEY set)
    brief = build_ai_brief(now, regime, breadth, overview, modes)

    print(f"Regime {regime}; Top 5:")
    for t in top5:
        print(f"  {t['kind']:12} {t['name']:38} score {t['score']:5.1f}  {t['signal']}")
    if not args.no_notify:
        send_daily_notification(now, regime, breadth, modes, top5, brief, funds)


def build_ai_brief(now, regime, breadth, overview, modes):
    """Generate and publish site/data/brief.json via Claude (if key present). Returns the brief dict or None."""
    try:
        import ai
        ctx = {"date": now.strftime("%d %b %Y"), "regime": regime,
               "breadth_above_200dma": round(breadth, 2) if breadth is not None else None,
               "advancers": overview["advancers"], "decliners": overview["decliners"],
               "snapshot": {k: (v and {"price": v["price"], "day_pct": round(v["day"] * 100, 2)}) for k, v in overview["snapshot"].items()},
               "trading_top5": [{"symbol": r["symbol"], "name": r["name"], "score": r["trading_score"],
                                 "verdict": r.get("trading_verdict_txt"), "buy_upto": r.get("trading_buy_upto"),
                                 "stop": r.get("trading_stop"), "rsi": r.get("rsi"), "day_pct": round((r.get("day_change") or 0) * 100, 2)}
                                for r in (modes.get("trading_top5", []) if modes else [])],
               "investing_top5": [{"symbol": r["symbol"], "name": r["name"], "score": r["investing_score"],
                                   "verdict": r.get("investing_verdict_txt"), "ret_1y_pct": round((r.get("ret_1y") or 0) * 100, 1),
                                   "sector": r.get("sector")}
                                  for r in (modes.get("investing_top5", []) if modes else [])]}
        brief = ai.market_brief(ctx)
        if brief:
            brief["generated_at"] = now.isoformat()
            (OUT / "brief.json").write_text(json.dumps(clean(brief)), encoding="utf-8")
            print("  AI brief written (model:", brief.get("model"), ")")
        return brief
    except Exception as ex:
        print("  ! AI brief skipped:", str(ex)[:140])
        return None


def send_daily_notification(now, regime, breadth, modes, top5, brief, funds=None):
    """Two daily pushes for the Indian market: a morning 'market open' alert and an evening
    'market closed' update, each with Indian stock shortlists (trading + investing) + top mutual funds."""
    is_open = now.hour < 12  # morning run ~09:15 IST = market open; evening ~17:00 = market closed
    when = "Market OPEN" if is_open else "Market CLOSED"
    title = f"{when} - {now:%d %b}"
    head = f"{when} · {regime}" + (f" · {breadth:.0%} of Indian stocks above their 200-day avg" if breadth is not None else "")
    lines = [head]
    if is_open:
        lines.append("Today's shortlist for Indian stocks & funds:")
    else:
        lines.append("End-of-day update — tomorrow's shortlist:")
    if brief and brief.get("brief"):
        lines.append(""); lines.append(brief["brief"])
    treasons = (brief or {}).get("trading_reasons", {})
    ireasons = (brief or {}).get("investing_reasons", {})
    tt = (modes or {}).get("trading_top5", [])
    it = (modes or {}).get("investing_top5", [])
    if tt:
        lines.append(""); lines.append("TRADING (short-term, Indian stocks):")
        for r in tt[:5]:
            why = treasons.get(r["symbol"]) or f"{r.get('trading_verdict_txt', 'setup')}"
            upto = f" (buy up to Rs {r['trading_buy_upto']:.0f})" if r.get("trading_buy_upto") else ""
            lines.append(f"- {r['name']}{upto} - {why}")
    if it:
        lines.append(""); lines.append("INVESTING (long-term, Indian stocks):")
        for r in it[:5]:
            why = ireasons.get(r["symbol"]) or f"{r.get('investing_verdict_txt', 'quality + trend')}"
            upto = f" (buy up to Rs {r['trading_buy_upto']:.0f})" if r.get("trading_buy_upto") else ""
            lines.append(f"- {r['name']} - {why}")
    # top mutual funds (diversified by category)
    tf = _distinct_category(funds or [])[:4]
    if tf:
        lines.append(""); lines.append("MUTUAL FUNDS (SIP/accumulate):")
        for f in tf:
            cagr = (f.get("cagr_3y") or f.get("ret_1y") or 0) * 100
            lines.append(f"- {f['name'].split(' - ')[0]} - 3Y return {cagr:.0f}%/yr")
    if not tt and not it and not tf:  # fallback
        for i, t in enumerate(top5, 1):
            lines.append(f"{i}. {t['name']} [{t['kind']}] {t['signal']}")
    lines.append(""); lines.append(DISCLAIMER)
    html = _email_html(now, is_open, when, regime, breadth, brief, tt, it, tf, treasons, ireasons)
    sent = N.send_all(title, "\n".join(lines), SITE_URL or None, html=html)
    print("Notified via:", sent or "nothing (no channel configured)")


def _email_html(now, is_open, when, regime, breadth, brief, tt, it, tf, treasons, ireasons):
    """A clean, mobile-friendly HTML email (inline styles for email-client compatibility)."""
    accent = "#0f766e"
    hero = "#065f46" if is_open else "#1e3a5f"
    regime_col = {"RISK-ON": "#16a34a", "RISK-OFF": "#dc2626"}.get(regime, "#d97706")
    url = SITE_URL or "https://aldrindsouza3-dotcom.github.io/market-tracker/"

    def chip(text, col):
        return f'<span style="background:{col};color:#fff;font-size:12px;font-weight:700;padding:2px 9px;border-radius:10px;white-space:nowrap">{text}</span>'

    def stock_row(r, reasons, is_trade):
        why = reasons.get(r["symbol"]) or (r.get("trading_verdict_txt") if is_trade else r.get("investing_verdict_txt")) or ""
        buy = r.get("trading_buy_upto")
        buy_html = f'<div style="font-size:13px;color:{accent};font-weight:700;margin-top:2px">Good to buy up to ₹{buy:,.0f}</div>' if buy else ""
        return (f'<tr><td style="padding:12px 14px;border-bottom:1px solid #eef2f6">'
                f'<div style="font-weight:700;color:#14181f;font-size:15px">{r["name"]}</div>'
                f'{buy_html}'
                f'<div style="font-size:13px;color:#667085;margin-top:3px">{why}</div></td></tr>')

    def section(title, emoji, rows_html, note):
        if not rows_html:
            return ""
        return (f'<tr><td style="padding:18px 0 6px"><div style="font-size:16px;font-weight:800;color:#14181f">{emoji} {title}</div>'
                f'<div style="font-size:12px;color:#98a2b3;margin-bottom:6px">{note}</div>'
                f'<table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #eef2f6;border-radius:10px;overflow:hidden">{rows_html}</table></td></tr>')

    trade_rows = "".join(stock_row(r, treasons, True) for r in tt[:5])
    invest_rows = "".join(stock_row(r, ireasons, False) for r in it[:5])
    fund_rows = ""
    for f in tf:
        cagr = (f.get("cagr_3y") or f.get("ret_1y") or 0) * 100
        fund_rows += (f'<tr><td style="padding:12px 14px;border-bottom:1px solid #eef2f6">'
                      f'<div style="font-weight:700;color:#14181f;font-size:15px">{f["name"].split(" - ")[0]}</div>'
                      f'<div style="font-size:13px;color:#16a34a;font-weight:700;margin-top:2px">3-year return: {cagr:.0f}% per year</div></td></tr>')

    brief_html = ""
    if brief and brief.get("brief"):
        brief_html = (f'<tr><td style="padding:4px 0 2px"><div style="background:#f0fdfa;border:1px solid #ccfbf1;border-radius:10px;padding:12px 14px">'
                      f'<div style="font-size:11px;font-weight:800;letter-spacing:.5px;color:{accent};text-transform:uppercase">✨ Market overview</div>'
                      f'<div style="font-size:14px;color:#14181f;margin-top:4px;line-height:1.5">{brief["brief"]}</div></div></td></tr>')

    breadth_txt = f"{breadth:.0%} of Indian stocks are above their 200-day average" if breadth is not None else ""
    good_news = ("Plenty of stocks are trending up — a good backdrop for buyers." if (breadth or 0) > 0.55
                 else "Be selective today — fewer stocks are trending up." if (breadth or 0) < 0.45
                 else "A mixed market — stick to the strongest names below.")
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f6f7f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7f9;padding:16px 0"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{hero};border-radius:14px 14px 0 0;padding:22px 20px">
    <div style="color:#fff;font-size:22px;font-weight:800">📈 Market Tracker</div>
    <div style="margin-top:8px">{chip(when, 'rgba(255,255,255,.22)')} &nbsp; {chip('Market: ' + regime, regime_col)}</div>
    <div style="color:#d1fae5;font-size:13px;margin-top:10px">{now:%A, %d %B %Y} · {breadth_txt}</div>
    <div style="color:#fff;font-size:14px;margin-top:4px;font-weight:600">{good_news}</div>
  </td></tr>
  <tr><td style="background:#fff;padding:14px 18px 20px;border-radius:0 0 0 0">
    <table width="100%" cellpadding="0" cellspacing="0">
      {brief_html}
      {section('Trading shortlist', '⚡', trade_rows, 'Short-term swing ideas (days to weeks) with buy-up-to prices')}
      {section('Investing shortlist', '◈', invest_rows, 'Long-term quality picks (months to years)')}
      {section('Mutual funds', '💰', fund_rows, 'For SIP / accumulation')}
    </table>
    <div style="text-align:center;margin-top:22px">
      <a href="{url}" style="background:{accent};color:#fff;text-decoration:none;font-weight:700;font-size:15px;padding:12px 26px;border-radius:10px;display:inline-block">Open the full dashboard →</a>
    </div>
    <div style="font-size:11px;color:#98a2b3;margin-top:18px;line-height:1.5;border-top:1px solid #eef2f6;padding-top:12px">
      Research aid, not investment advice — the author is not a SEBI-registered adviser. End-of-day data; verify before investing. Prices are in ₹ (INR).
    </div>
  </td></tr>
</table></td></tr></table></body></html>"""


def build_full_universe(now):
    """Publish site/data/universe.json: every NSE equity, searchable, with the liquidity gate + reason.
    Fully isolated — any failure here must not stop the main run."""
    try:
        import nse
        s = nse.session()
        recent = nse.recent_bhavcopies(22, s)
        if not recent:
            print("  ! universe: no bhavcopy available (NSE/BSE unreachable); keeping previous")
            return
        asof = recent[0][0]
        sec = nse.securities(s)
        uni = nse.build_universe(recent, sec)
        elig = [u for u in uni if u["eligible"]]
        # data-quality health check
        stale_days = (now.date() - asof).days
        absurd = [u["symbol"] for u in uni if u["day_change"] is not None and abs(u["day_change"]) > 0.35]
        missing_close = sum(1 for u in uni if u["close"] is None)
        issues = []
        if stale_days > 4:
            issues.append(f"Data is {stale_days} days old")
        if len(absurd) > 30:
            issues.append(f"{len(absurd)} stocks moved >35% (possible unadjusted corporate actions)")
        if missing_close > 50:
            issues.append(f"{missing_close} symbols missing close")
        health = {"status": "ok" if not issues else "warn", "asof": asof.isoformat(),
                  "stale_days": stale_days, "absurd_moves": len(absurd), "issues": issues}
        payload = {"generated_at": now.isoformat(), "asof": asof.isoformat(), "source": recent[0][1]["source"].iloc[0],
                   "total": len(uni), "eligible": len(elig), "sme": sum(1 for u in uni if u["board"] == "SME"),
                   "gate": "Median 20-day turnover >= Rs 1 cr, price >= Rs 10, mainboard, not SME/surveillance",
                   "health": health, "symbols": uni}
        (OUT / "universe.json").write_text(json.dumps(clean(payload), indent=0), encoding="utf-8")
        print(f"  universe: {len(uni)} symbols ({len(elig)} eligible) as of {asof}")
    except Exception as ex:
        print("  ! universe build failed (non-fatal):", str(ex)[:160])


def append_history(now, regime, breadth, nifty, indices, commodities, currencies, adv, dec):
    """One row per day, so the Overview tab can draw trend lines that grow over time."""
    f = OUT / "history.json"
    hist = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    day = now.strftime("%Y-%m-%d")
    g = lambda sym, lst: next((x["price"] for x in lst if x["symbol"] == sym), None)
    row = {"date": day, "regime": regime, "breadth": round(breadth, 3) if breadth is not None else None,
           "nifty": nifty["price"] if nifty else None, "sensex": g("^BSESN", indices),
           "gold": g("GC=F", commodities), "silver": g("SI=F", commodities), "usdinr": g("USDINR=X", currencies),
           "advancers": adv, "decliners": dec}
    hist = [h for h in hist if h["date"] != day] + [row]
    f.write_text(json.dumps(clean(hist[-400:]), indent=1), encoding="utf-8")


def _distinct_category(funds):
    seen, out = set(), []
    for f in funds:  # one fund per category so two gold funds don't fill the Top 5
        key = f["category"] or f["name"]
        if key not in seen:
            seen.add(key); out.append(f)
    return out


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def update_track_record(now, top5, px):
    """Append today's picks and mark earlier picks to market so you can see whether the rules actually work."""
    f = OUT / "track_record.json"
    rec = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"picks": []}
    today = now.strftime("%Y-%m-%d")
    if not any(p["date"] == today for p in rec["picks"]):
        for t in top5:
            if t["kind"] in ("Stock", "Commodity") and t.get("stop_loss"):
                rec["picks"].append({"date": today, "symbol": t["symbol"], "name": t["name"], "entry": t["price"],
                                     "stop": t["stop_loss"], "target": t["target_1"], "status": "OPEN"})
    for p in rec["picks"]:
        if p["status"] != "OPEN" or p["symbol"] not in px:
            continue
        df = px[p["symbol"]]
        after = df[df.index > p["date"]]
        for _, row in after.iterrows():  # conservative: stop checked before target within the same day
            if row["Low"] <= p["stop"]:
                p.update(status="STOPPED", exit=p["stop"]); break
            if row["High"] >= p["target"]:
                p.update(status="TARGET HIT", exit=p["target"]); break
        p["last"] = float(df["Close"].iloc[-1])
        p["pnl_pct"] = round(((p.get("exit") or p["last"]) / p["entry"] - 1) * 100, 2)
    rec["picks"] = rec["picks"][-400:]
    closed = [p for p in rec["picks"] if p["status"] != "OPEN"]
    rec["summary"] = {"total": len(rec["picks"]), "open": len(rec["picks"]) - len(closed),
                      "hit_rate": round(sum(p["status"] == "TARGET HIT" for p in closed) / len(closed), 3) if closed else None}
    f.write_text(json.dumps(clean(rec), indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
