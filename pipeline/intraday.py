"""Near-live intraday price refresh (~15 min delayed) for Indian market hours.

A LIGHT job (no scoring, no bhavcopy): just pulls delayed quotes for key indices, commodities, FX and
today's shortlisted picks, and writes site/data/live.json. The app reads this file from the GitHub raw URL,
so it updates without a full site redeploy. Runs every ~30 min on weekdays via its own workflow.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"

INDICES = {"^NSEI": "Nifty 50", "^BSESN": "Sensex", "^NSEBANK": "Bank Nifty",
           "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^N225": "Nikkei"}
COMMODITIES = {"GC=F": "Gold ($)", "SI=F": "Silver ($)", "CL=F": "Crude ($)"}
FX = {"USDINR=X": "USD/INR"}


def _col(df, sym, col="Close"):
    try:
        s = df[sym][col] if hasattr(df.columns, "levels") else df[col]
        s = s.dropna()
        return s
    except Exception:
        import pandas as pd
        return pd.Series(dtype=float)


def build():
    import yfinance as yf
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    try:
        modes = json.loads((OUT / "modes.json").read_text(encoding="utf-8"))
    except Exception:
        modes = {}
    picks, seen = [], set()
    for r in (modes.get("trading_top5", []) + modes.get("investing_top5", [])):
        if r["symbol"] in seen:
            continue
        seen.add(r["symbol"]); picks.append(r)
    pick_map = {f"{r['symbol']}.NS": r for r in picks}
    allsyms = list(INDICES) + list(COMMODITIES) + list(FX) + list(pick_map)

    try:
        intr = yf.download(allsyms, period="1d", interval="15m", group_by="ticker", progress=False, threads=True)
    except Exception:
        intr = None
    try:
        daily = yf.download(allsyms, period="7d", interval="1d", group_by="ticker", progress=False, threads=True)
    except Exception:
        daily = None

    def quote(sym):
        cur = None
        if intr is not None:
            s = _col(intr, sym)
            cur = float(s.iloc[-1]) if len(s) else None
        prev = None
        if daily is not None:
            s = _col(daily, sym)
            if len(s) >= 2:
                prev = float(s.iloc[-2])
            elif len(s):
                prev = float(s.iloc[-1])
        if cur is None:
            cur = prev
        chg = (cur / prev - 1) if (cur and prev) else None
        return (round(cur, 2) if cur is not None else None), chg

    def pack(d):
        out = []
        for sym, name in d.items():
            c, ch = quote(sym)
            if c is not None:
                out.append({"symbol": sym, "name": name, "price": c, "change": ch})
        return out

    live_picks = []
    for sym, r in pick_map.items():
        c, ch = quote(sym)
        if c is not None:
            live_picks.append({"symbol": r["symbol"], "name": r["name"], "price": c, "change": ch,
                               "buy_upto": r.get("trading_buy_upto"),
                               "verdict": r.get("trading_verdict_txt") or r.get("investing_verdict_txt")})

    market_open = now.weekday() < 5 and dt.time(9, 15) <= now.time() <= dt.time(15, 30)
    data = {"updated_at": now.isoformat(), "market_open": market_open, "delay_note": "about 15 minutes delayed",
            "indices": pack(INDICES), "commodities": pack(COMMODITIES), "fx": pack(FX), "picks": live_picks}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "live.json").write_text(json.dumps(data), encoding="utf-8")
    print(f"live.json written; market_open={market_open}; {len(live_picks)} picks, "
          f"{len(data['indices'])} indices")


if __name__ == "__main__":
    build()
