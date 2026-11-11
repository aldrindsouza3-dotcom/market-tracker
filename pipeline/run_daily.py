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

    out = {"generated_at": now.isoformat(), "asof_note": "End-of-day data (Yahoo Finance, delayed). Prices in local currency; INR for India.",
           "regime": regime, "breadth_above_200dma": breadth, "top5": top5, "stocks": stocks, "indices": indices,
           "commodities": commodities, "currencies": currencies, "yields": yields, "mutual_funds": funds,
           "ipos": ipos, "news": news, "data_gaps": gaps, "disclaimer": DISCLAIMER}
    (OUT / "latest.json").write_text(json.dumps(clean(out), indent=1), encoding="utf-8")

    update_track_record(now, top5, px)

    print(f"Regime {regime}; Top 5:")
    for t in top5:
        print(f"  {t['kind']:12} {t['name']:38} score {t['score']:5.1f}  {t['signal']}")
    if not args.no_notify:
        lines = [f"Market: {regime} (Nifty-50 above 200DMA: {breadth:.0%})" if breadth is not None else f"Market: {regime}"]
        for i, t in enumerate(top5, 1):
            lvl = ""
            if t.get("stop_loss"):
                lvl = f" | buy {t['entry_low']:.0f}-{t['entry_high']:.0f}, SL {t['stop_loss']:.0f}, T1 {t['target_1']:.0f}"
            lines.append(f"{i}. {t['name']} [{t['kind']}] {t['signal']}{lvl}")
        lines.append(DISCLAIMER)
        sent = N.send_all(f"Top 5 picks - {now:%d %b}", "\n".join(lines), SITE_URL or None)
        print("Notified via:", sent or "nothing (no channel configured)")


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
