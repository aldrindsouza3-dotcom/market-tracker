"""Per-symbol daily history store (hybrid): seed long history from Yahoo once, then maintain from the
whole-market NSE bhavcopy (one request/day, adds delivery %). Files live in cache/hist/ (gitignored,
persisted via GitHub Actions cache). This avoids per-ticker downloads on every run.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nse import CACHE

HIST = CACHE / "hist"
HIST.mkdir(parents=True, exist_ok=True)
COLS = ["date", "open", "high", "low", "close", "volume", "deliv_pct"]


def _path(sym: str) -> Path:
    return HIST / f"{sym}.parquet"


def load(sym: str) -> pd.DataFrame | None:
    p = _path(sym)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def save(sym: str, df: pd.DataFrame) -> None:
    df = df.dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
    try:
        df[COLS].to_parquet(_path(sym), index=False)
    except Exception:
        pass


def have(sym: str) -> bool:
    return _path(sym).exists()


def seed_from_yahoo(symbols: list[str], limit: int, period: str = "3y") -> int:
    """Download long history for up to `limit` symbols that aren't cached yet. Returns count seeded."""
    import yfinance as yf

    todo = [s for s in symbols if not have(s)][:limit]
    if not todo:
        return 0
    seeded = 0
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        try:
            raw = yf.download([f"{s}.NS" for s in chunk], period=period, interval="1d",
                              group_by="ticker", auto_adjust=True, progress=False, threads=True)
        except Exception:
            continue
        for s in chunk:
            try:
                d = raw[f"{s}.NS"] if len(chunk) > 1 else raw
                d = d.dropna(subset=["Close"])
                if len(d) < 60:
                    continue
                out = pd.DataFrame({
                    "date": [x.date().isoformat() for x in d.index],
                    "open": d["Open"].values, "high": d["High"].values, "low": d["Low"].values,
                    "close": d["Close"].values, "volume": d["Volume"].values, "deliv_pct": None,
                })
                save(s, out)
                seeded += 1
            except Exception:
                pass
    return seeded


def append_bhav_day(bhav: pd.DataFrame) -> int:
    """Append one trading day (from a whole-market bhavcopy) to every cached symbol. Returns rows added."""
    if bhav is None or not len(bhav):
        return 0
    day = str(bhav["date"].iloc[0])
    by = {r["symbol"]: r for _, r in bhav.iterrows()}
    n = 0
    for p in HIST.glob("*.parquet"):
        sym = p.stem
        if sym not in by:
            continue
        df = load(sym)
        if df is None or (len(df) and df["date"].iloc[-1] >= day):
            continue
        r = by[sym]
        row = {"date": day, "open": r["open"], "high": r["high"], "low": r["low"],
               "close": r["close"], "volume": r["volume"],
               "deliv_pct": r.get("deliv_pct") if "deliv_pct" in bhav.columns else None}
        save(sym, pd.concat([df, pd.DataFrame([row])], ignore_index=True))
        n += 1
    return n


def to_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Shape a stored history into the OHLCV frame the analysis/indicator code expects (DatetimeIndex)."""
    out = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}).copy()
    out.index = pd.to_datetime(df["date"])
    return out
