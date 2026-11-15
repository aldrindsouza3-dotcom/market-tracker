"""US & global large-cap stocks + ETFs, scored like the Indian universe (via Yahoo Finance).

Small curated universe (~80), so we fetch history directly each run (fast). Writes:
  site/data/us/<SYM>.json   per-symbol detail (chart + reading + scores + beta/alpha vs S&P 500 + fundamentals)
  site/data/us_index.json   the scored list for the US tab + screener
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd

import nse
import scoring as SC

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
US = OUT / "us"
FUND_CACHE = nse.CACHE / "us_fundamentals.json"
FUND_PER_RUN = 40

# Curated US/global large caps + popular ETFs (Yahoo symbols). Edit freely.
UNIVERSE = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon", "NVDA": "NVIDIA",
    "META": "Meta Platforms", "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway", "JPM": "JPMorgan Chase",
    "V": "Visa", "MA": "Mastercard", "UNH": "UnitedHealth", "JNJ": "Johnson & Johnson", "WMT": "Walmart",
    "PG": "Procter & Gamble", "HD": "Home Depot", "COST": "Costco", "ORCL": "Oracle", "KO": "Coca-Cola",
    "PEP": "PepsiCo", "ADBE": "Adobe", "CRM": "Salesforce", "NFLX": "Netflix", "AMD": "AMD",
    "INTC": "Intel", "CSCO": "Cisco", "MCD": "McDonald's", "DIS": "Disney", "NKE": "Nike", "BA": "Boeing",
    "XOM": "ExxonMobil", "CVX": "Chevron", "PFE": "Pfizer", "MRK": "Merck", "ABBV": "AbbVie", "LLY": "Eli Lilly",
    "TMO": "Thermo Fisher", "AVGO": "Broadcom", "QCOM": "Qualcomm", "TXN": "Texas Instruments",
    "HON": "Honeywell", "CAT": "Caterpillar", "GE": "GE Aerospace", "UPS": "UPS", "GS": "Goldman Sachs",
    "MS": "Morgan Stanley", "BAC": "Bank of America", "WFC": "Wells Fargo", "C": "Citigroup", "T": "AT&T",
    "VZ": "Verizon", "CMCSA": "Comcast", "PYPL": "PayPal", "SBUX": "Starbucks", "BKNG": "Booking",
    "NOW": "ServiceNow", "INTU": "Intuit", "AMAT": "Applied Materials", "MU": "Micron", "PLTR": "Palantir",
    # global / ADRs
    "TSM": "TSMC (Taiwan)", "BABA": "Alibaba (China)", "TM": "Toyota (Japan)", "SONY": "Sony (Japan)",
    "SHEL": "Shell (UK)", "HSBC": "HSBC (UK)", "NVO": "Novo Nordisk (Denmark)", "ASML": "ASML (Netherlands)",
    # ETFs
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF", "VTI": "Total US Market ETF", "GLD": "Gold ETF",
    "SLV": "Silver ETF", "IWM": "US Small-Cap ETF", "EEM": "Emerging Markets ETF", "VXUS": "Intl ex-US ETF",
}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _compact(df, max_rows=1300):
    d = df.tail(max_rows)
    r2 = lambda s: [None if pd.isna(x) else round(float(x), 2) for x in s]
    return {"t": [x.date().isoformat() for x in d.index], "o": r2(d["Open"]), "h": r2(d["High"]),
            "l": r2(d["Low"]), "c": r2(d["Close"]), "v": [None if pd.isna(x) else int(x) for x in d["Volume"]], "dp": []}


def build(now: dt.datetime):
    try:
        import yfinance as yf
        US.mkdir(parents=True, exist_ok=True)
        syms = list(UNIVERSE)
        print(f"US: downloading {len(syms)} symbols...")
        raw = yf.download(syms, period="3y", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=True)
        # S&P 500 daily returns for beta/alpha
        spx_ret = {}
        try:
            sp = raw["SPY"]["Close"].dropna() if "SPY" in syms else None
            if sp is not None:
                prev = None
                for ts, v in sp.items():
                    if prev:
                        spx_ret[ts.date().isoformat()] = float(v) / prev - 1
                    prev = float(v)
        except Exception:
            pass

        fcache = json.loads(FUND_CACHE.read_text(encoding="utf-8")) if FUND_CACHE.exists() else {}
        stale = [s for s in syms if now.isoformat()[:10] > fcache.get(s, {}).get("asof", "0000")[:10]]
        for s in stale[:FUND_PER_RUN]:
            try:
                i = yf.Ticker(s).info or {}
                fcache[s] = {"pe": i.get("trailingPE"), "roe": i.get("returnOnEquity"), "debt_equity": i.get("debtToEquity"),
                             "rev_growth": i.get("revenueGrowth"), "profit_margin": i.get("profitMargins"),
                             "div_yield": i.get("dividendYield"), "sector": i.get("sector"), "asof": now.isoformat()}
            except Exception:
                pass
        try:
            FUND_CACHE.write_text(json.dumps(fcache), encoding="utf-8")
        except Exception:
            pass

        rows, scored = [], 0
        for s in syms:
            try:
                df = raw[s] if len(syms) > 1 else raw
                df = df.dropna(subset=["Close"])
                if len(df) < 120:
                    continue
                t = SC.indicators(df)
                if not t:
                    continue
                f = fcache.get(s)
                tscore = SC.trading_score(t)
                iscore, had_f = SC.investing_score(t, f)
                tplan = SC.trading_plan(t, tscore)
                iplan = SC.investing_plan(t, f, iscore)
                reading = SC.chart_reading(df, t)
                risk = SC.risk_metrics(df["Close"].tolist(), [x.date().isoformat() for x in df.index], spx_ret) if spx_ret else {}
                name = UNIVERSE[s]
                rows.append({"symbol": s, "name": name, "sector": (f or {}).get("sector"),
                             "close": round(t["price"], 2), "day_change": t["day_change"],
                             "trading_score": tscore, "investing_score": iscore,
                             "trading_verdict": tplan["verdict_class"], "investing_verdict": iplan["verdict_class"],
                             "trading_verdict_txt": tplan["verdict"], "trading_buy_upto": tplan["buy_upto"],
                             "trading_stop": tplan["stop_loss"], "trading_t1": tplan["target_1"],
                             "investing_verdict_txt": iplan["verdict"], "rsi": round(t["rsi"], 0),
                             "ret_1y": t["ret_1y"], "pe": (f or {}).get("pe"), "roe": (f or {}).get("roe"),
                             "rev_growth": (f or {}).get("rev_growth")})
                detail = {"symbol": s, "name": name, "asof": str(df.index[-1].date()), "source": "Yahoo Finance",
                          "currency": "USD", "price": round(t["price"], 2), "day_change": t["day_change"], "days_history": t["days"],
                          "indicators": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()},
                          "trading": {"score": tscore, **tplan}, "investing": {"score": iscore, "has_fundamentals": had_f, **iplan},
                          "reading": reading, "risk": risk, "fundamentals": f, "fundamental_analysis": SC.fundamental_analysis(f),
                          "links": {"tickertape": None, "screener": None,
                                    "moneycontrol": f"https://finance.yahoo.com/quote/{s}"},
                          "ohlc": _compact(df), "disclaimer": "Research aid, not advice. End-of-day data. Prices in USD."}
                (US / f"{s}.json").write_text(json.dumps(_clean(detail)), encoding="utf-8")
                scored += 1
            except Exception as ex:
                print(f"  . US skip {s}: {str(ex)[:60]}")
        rows.sort(key=lambda r: -(r["trading_score"] + r["investing_score"]))
        (OUT / "us_index.json").write_text(json.dumps(_clean({
            "generated_at": now.isoformat(), "count": len(rows), "currency": "USD",
            "note": "US & global large caps + ETFs, scored via Yahoo Finance.", "rows": rows})), encoding="utf-8")
        print(f"US: scored {scored} symbols")
    except Exception as ex:
        import traceback
        print("  ! US build failed (non-fatal):", str(ex)[:160])
        traceback.print_exc()
