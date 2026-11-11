"""Network fetchers: Yahoo Finance (prices, fundamentals), mfapi.in (mutual funds), IPO list (best effort)."""
from __future__ import annotations

import io
import re
import time

import pandas as pd
import requests
import yfinance as yf

UA = {"User-Agent": "Mozilla/5.0 (market-tracker)"}


def prices(symbols: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Batch download daily OHLCV. Returns {symbol: df}; symbols with no data are omitted."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), 40):
        chunk = symbols[i:i + 40]
        try:
            raw = yf.download(chunk, period=period, interval="1d", group_by="ticker",
                              auto_adjust=True, progress=False, threads=True)
        except Exception as e:  # network hiccup: skip chunk, pipeline reports gaps
            print(f"  ! download failed for {chunk[:3]}...: {e}")
            continue
        for s in chunk:
            try:
                df = raw[s] if len(chunk) > 1 else raw
                df = df.dropna(subset=["Close"])
                if len(df):
                    out[s] = df
            except Exception:
                pass
    return out


def fundamentals(symbol: str) -> dict | None:
    try:
        i = yf.Ticker(symbol).info
    except Exception:
        return None
    if not i:
        return None
    return {
        "pe": i.get("trailingPE"), "fwd_pe": i.get("forwardPE"), "roe": i.get("returnOnEquity"),
        "debt_equity": i.get("debtToEquity"), "rev_growth": i.get("revenueGrowth"),
        "profit_margin": i.get("profitMargins"), "div_yield": i.get("dividendYield"),
        "market_cap": i.get("marketCap"), "sector": i.get("sector"),
    }


def mf_nav_history(query: str) -> tuple[dict, pd.Series] | None:
    """Resolve a fund by name on mfapi.in, return (meta, NAV series ascending)."""
    try:
        res = requests.get("https://api.mfapi.in/mf/search", params={"q": query}, headers=UA, timeout=25).json()
        want = query.lower()
        direct = [r for r in res if "direct" in r["schemeName"].lower() and "growth" in r["schemeName"].lower()
                  and "idcw" not in r["schemeName"].lower()]
        pick = next((r for r in direct if r["schemeName"].lower().replace("-", "").replace("  ", " ")
                     .startswith(want.split(" direct")[0][:25])), None) or (direct[0] if direct else None)
        if not pick:
            return None
        d = requests.get(f"https://api.mfapi.in/mf/{pick['schemeCode']}", headers=UA, timeout=40).json()
        s = pd.Series({pd.to_datetime(x["date"], format="%d-%m-%Y"): float(x["nav"]) for x in d["data"]}).sort_index()
        return {"code": pick["schemeCode"], "name": pick["schemeName"], "category": d["meta"].get("scheme_category", "")}, s
    except Exception as e:
        print(f"  ! MF {query}: {e}")
        return None


def _d(x):
    return re.sub(r"\s*GMP:.*", "", x)


def upcoming_ipos() -> dict:
    """Best-effort IPO list from investorgain.com (unofficial; includes grey-market premium, GMP).
    On failure ok=False and the dashboard shows manual links instead."""
    links = ["https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
             "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/"]
    try:
        html = requests.get("https://www.investorgain.com/report/live-ipo-gmp/331/", timeout=25,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}).text
        t = pd.read_html(io.StringIO(html))[0]
        t.columns = [re.sub(r"[▲▼]|🔥", "", str(c)).strip() for c in t.columns]
        t = t.dropna(subset=["Name"]).head(40)
        rows = []
        for r in t.fillna("").astype(str).to_dict("records"):
            name = re.sub(r"\[email.*$", "", r["Name"]).strip()
            board = "SME" if "SME" in r["Name"] else "Mainboard"
            rows.append({"Name": name, "Board": board, "Price (Rs)": r.get("Price (₹)", ""), "Size": r.get("IPO Size", ""),
                         "Lot": r.get("Lot", ""), "Open": _d(r.get("Open", "")), "Close": _d(r.get("Close", "")),
                         "Listing": _d(r.get("Listing", "")), "Subscription": r.get("Sub", ""), "GMP (unofficial)": r.get("GMP", "")})
        if not rows:
            raise ValueError("no rows")
        return {"ok": True, "source": "investorgain.com", "rows": rows, "manual_links": links}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "rows": [], "manual_links": links}


def headlines(query: str, n: int = 6) -> list[dict]:
    """Google News RSS headlines, for context only (not scored)."""
    try:
        xml = requests.get("https://news.google.com/rss/search", headers=UA, timeout=20,
                           params={"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}).text
        items = re.findall(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>", xml, re.S)[:n]
        clean = lambda s: re.sub(r"<!\[CDATA\[|\]\]>", "", s).replace("&amp;", "&").replace("&#39;", "'").strip()
        return [{"title": clean(t), "link": clean(l)} for t, l in items]
    except Exception:
        return []
