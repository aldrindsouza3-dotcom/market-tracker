"""NSE data layer: securities list + daily bhavcopy (UDiFF) + delivery %, with BSE fallback and caching.

One bhavcopy covers the whole market, so we never download per-ticker for Indian equities.
NSE blocks some cloud IPs unless you warm up cookies and send browser-like headers; we do both,
retry, fall back to BSE, and fall back to the last good cache so a bad fetch never publishes nothing.

Cache lives in pipeline/../cache/ (gitignored). History store (committed, compact) in site/data/history/.
"""
from __future__ import annotations

import datetime as dt
import io
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)

_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAINBOARD = {"EQ", "BE"}  # tradable mainboard equity series
SME = {"SM", "ST"}        # SME/Emerge series (flagged separately)
EQUITY_SERIES = MAINBOARD | SME


def session() -> requests.Session:
    """A session with NSE cookies warmed up (needed from datacentre IPs)."""
    s = requests.Session()
    s.headers.update(_BROWSER)
    for host in ("https://www.nseindia.com/", "https://www.nseindia.com/market-data/securities-available-for-trading"):
        try:
            s.get(host, timeout=20)
        except Exception:
            pass
    return s


def _get(s: requests.Session, url: str, referer: str, tries: int = 3, **kw) -> requests.Response | None:
    for i in range(tries):
        try:
            r = s.get(url, headers={"Referer": referer}, timeout=35, **kw)
            if r.status_code == 200 and r.content:
                return r
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    return None


# ---------------- securities master (names / ISIN) ----------------
def securities(s: requests.Session | None = None, max_age_days: int = 7) -> pd.DataFrame:
    """EQUITY_L.csv (mainboard names/ISIN/series), cached weekly. Columns: symbol,name,series,isin,listed."""
    cf = CACHE / "equity_l.csv"
    if cf.exists() and (time.time() - cf.stat().st_mtime) < max_age_days * 86400:
        return pd.read_csv(cf)
    s = s or session()
    r = _get(s, "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", "https://www.nseindia.com/")
    if r is None:
        return pd.read_csv(cf) if cf.exists() else pd.DataFrame(columns=["symbol", "name", "series", "isin", "listed"])
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame({
        "symbol": df["SYMBOL"].astype(str).str.strip(),
        "name": df["NAME OF COMPANY"].astype(str).str.strip(),
        "series": df["SERIES"].astype(str).str.strip(),
        "isin": df["ISIN NUMBER"].astype(str).str.strip(),
        "listed": df["DATE OF LISTING"].astype(str).str.strip(),
    })
    out.to_csv(cf, index=False)
    return out


# ---------------- daily bhavcopy (whole market) ----------------
def _nse_udiff(s: requests.Session, d: dt.date) -> pd.DataFrame | None:
    u = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    r = _get(s, u, "https://www.nseindia.com/all-reports")
    if r is None:
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        df = pd.read_csv(z.open(z.namelist()[0]))
    except Exception:
        return None
    df = df[df["SctySrs"].isin(EQUITY_SERIES)].copy()
    out = pd.DataFrame({
        "symbol": df["TckrSymb"].astype(str).str.strip(),
        "series": df["SctySrs"].astype(str).str.strip(),
        "isin": df["ISIN"].astype(str).str.strip(),
        "open": df["OpnPric"], "high": df["HghPric"], "low": df["LwPric"], "close": df["ClsPric"],
        "prev_close": df["PrvsClsgPric"], "volume": df["TtlTradgVol"], "turnover": df["TtlTrfVal"],
        "trades": df.get("TtlNbOfTxsExctd"),
    })
    out["date"] = d.isoformat()
    out["source"] = "NSE"
    return out


def _bse_bhav(s: requests.Session, d: dt.date) -> pd.DataFrame | None:
    u = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
    r = _get(s, u, "https://www.bseindia.com/")
    if r is None:
        return None
    try:
        df = pd.read_csv(io.StringIO(r.text))
    except Exception:
        return None
    df = df[df["SctySrs"].astype(str).str.strip().isin({"A", "B", "T", "EQ", "BE"})].copy()
    out = pd.DataFrame({
        "symbol": df["TckrSymb"].astype(str).str.strip() if "TckrSymb" in df else df.get("SC_NAME"),
        "series": df.get("SctySrs"), "isin": df.get("ISIN"),
        "open": df["OpnPric"], "high": df["HghPric"], "low": df["LwPric"], "close": df["ClsPric"],
        "prev_close": df.get("PrvsClsgPric"), "volume": df.get("TtlTradgVol"), "turnover": df.get("TtlTrfVal"),
    })
    out["date"] = d.isoformat()
    out["source"] = "BSE"
    return out


def _delivery(s: requests.Session, d: dt.date) -> pd.DataFrame | None:
    """sec_bhavdata_full: adds delivery quantity / delivery %."""
    u = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
    r = _get(s, u, "https://www.nseindia.com/all-reports")
    if r is None:
        return None
    try:
        df = pd.read_csv(io.StringIO(r.text))
    except Exception:
        return None
    df.columns = [c.strip() for c in df.columns]
    if "DELIV_PER" not in df.columns:
        return None
    return pd.DataFrame({
        "symbol": df["SYMBOL"].astype(str).str.strip(), "series": df["SERIES"].astype(str).str.strip(),
        "deliv_qty": pd.to_numeric(df.get("DELIV_QTY"), errors="coerce"),
        "deliv_pct": pd.to_numeric(df["DELIV_PER"], errors="coerce"),
    })


def bhavcopy(d: dt.date, s: requests.Session | None = None, with_delivery: bool = True) -> pd.DataFrame | None:
    """Whole-market OHLCV for date d. Tries NSE, then BSE, then the cached copy. Adds delivery % when available."""
    cf = CACHE / f"bhav_{d:%Y%m%d}.parquet"
    if cf.exists():
        return pd.read_parquet(cf)
    s = s or session()
    df = _nse_udiff(s, d)
    if df is None:
        df = _bse_bhav(s, d)
    if df is None:
        return None
    for col in ("open", "high", "low", "close", "prev_close", "volume", "turnover"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if with_delivery and df["source"].iloc[0] == "NSE":
        dd = _delivery(s, d)
        if dd is not None:
            df = df.merge(dd[["symbol", "deliv_pct", "deliv_qty"]], on="symbol", how="left")
    try:
        df.to_parquet(cf, index=False)
    except Exception:
        pass
    return df


def latest_bhavcopy(s: requests.Session | None = None, back: int = 7):
    """Most recent available trading day's bhavcopy. Returns (date, df) or (None, None)."""
    s = s or session()
    for i in range(1, back + 1):
        d = dt.date.today() - dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        df = bhavcopy(d, s)
        if df is not None and len(df) > 500:
            return d, df
    return None, None


# ---------------- liquidity gate ----------------
def liquidity_gate(med_turnover_20d: float, last_price: float, days_history: int,
                   series: str, min_turnover_cr: float = 5.0, min_price: float = 10.0,
                   restricted: bool = False) -> tuple[bool, str]:
    """Eligible for recommendations? Returns (ok, reason-if-not)."""
    if series in SME:
        return False, "SME board (thin trading)"
    if restricted:
        return False, "In ASM/GSM/surveillance"
    if days_history < 200:
        return False, "Under 200 days of history"
    if last_price < min_price:
        return False, f"Price below Rs {min_price:.0f}"
    if med_turnover_20d < min_turnover_cr * 1e7:
        return False, f"Median 20-day turnover under Rs {min_turnover_cr:.0f} cr"
    return True, ""
