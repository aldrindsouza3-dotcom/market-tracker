"""Honest backtest of the Trading rule over the stored per-symbol history.

Rules tested (a transparent proxy of the live Trading signal):
  Enter when close > SMA50 and close > SMA200 and 50 <= RSI(14) <= 68 and close > yesterday.
  Entry at the NEXT session's open (not the signal-day close). Stop = entry - 1.8*ATR,
  target = entry + 2.7*ATR, time-stop 15 sessions. One open trade per symbol at a time.
  A round-trip cost (brokerage+slippage) is subtracted from every trade.

Published to site/data/backtest.json and compared with buy-and-hold Nifty 50 over the same span.
Refreshed weekly (it's slow); cached in cache/backtest.json.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

import nse
import store

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
CACHE_BT = nse.CACHE / "backtest.json"
COST = 0.004  # 0.4% round-trip brokerage + slippage assumption


def _rsi_series(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50)


def _atr_series(h, l, c, n: int = 14) -> pd.Series:
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _symbol_trades(df: pd.DataFrame) -> list[float]:
    """Return list of per-trade net returns (fraction) for one symbol."""
    if len(df) < 230:
        return []
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    sma50 = c.rolling(50).mean(); sma200 = c.rolling(200).mean()
    rsi = _rsi_series(c); atr = _atr_series(h, l, c)
    n = len(df)
    trades, i = [], 210
    o_, h_, l_, c_ = o.values, h.values, l.values, c.values
    s50, s200, rs, at = sma50.values, sma200.values, rsi.values, atr.values
    while i < n - 16:
        if (c_[i] > s50[i] and c_[i] > s200[i] and 50 <= rs[i] <= 68 and c_[i] > c_[i - 1]
                and not np.isnan(s200[i]) and at[i] > 0):
            entry = o_[i + 1]
            if not entry or np.isnan(entry):
                i += 1; continue
            stop = entry - 1.8 * at[i]; target = entry + 2.7 * at[i]
            exit_px, j = c_[min(i + 15, n - 1)], i + 1
            while j <= min(i + 15, n - 1):
                if l_[j] <= stop:
                    exit_px = stop; break
                if h_[j] >= target:
                    exit_px = target; break
                j += 1
            trades.append((exit_px / entry - 1) - COST)
            i = j + 1  # no overlapping trades
        else:
            i += 1
    return trades


def _nifty_return(s) -> float | None:
    try:
        import yfinance as yf
        d = yf.download("^NSEI", period="3y", interval="1d", auto_adjust=True, progress=False)
        c = d["Close"]
        if hasattr(c, "columns"):
            c = c.iloc[:, 0]
        c = c.dropna()
        return float(c.iloc[-1] / c.iloc[0] - 1) if len(c) else None
    except Exception:
        return None


def run(now: dt.datetime, max_age_days: int = 7, limit: int | None = None) -> dict | None:
    """Backtest across all symbols in the history store. Cached weekly."""
    if CACHE_BT.exists() and (time.time() - CACHE_BT.stat().st_mtime) < max_age_days * 86400:
        try:
            cached = json.loads(CACHE_BT.read_text(encoding="utf-8"))
            (OUT / "backtest.json").write_text(json.dumps(cached), encoding="utf-8")
            return cached
        except Exception:
            pass
    files = sorted(store.HIST.glob("*.parquet"))
    if limit:
        files = files[:limit]
    all_r, per_symbol = [], 0
    for p in files:
        df = store.load(p.stem)
        if df is None:
            continue
        tr = _symbol_trades(df)
        if tr:
            all_r.extend(tr); per_symbol += 1
    if not all_r:
        return None
    r = np.array(all_r)
    wins = r[r > 0]; losses = r[r <= 0]
    # sequential equity curve for drawdown
    eq = np.cumprod(1 + r); peak = np.maximum.accumulate(eq)
    maxdd = float(((eq - peak) / peak).min())
    nifty = _nifty_return(None)
    strat_cagr = float(eq[-1] ** (1 / 3) - 1) if len(eq) else None  # rough, ~3y span
    out = {"generated_at": now.isoformat(), "symbols_tested": per_symbol, "trades": int(len(r)),
           "win_rate": round(float((r > 0).mean()), 3),
           "avg_win_pct": round(float(wins.mean() * 100), 2) if len(wins) else 0,
           "avg_loss_pct": round(float(losses.mean() * 100), 2) if len(losses) else 0,
           "expectancy_pct": round(float(r.mean() * 100), 2),
           "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() < 0 else None,
           "max_drawdown_pct": round(maxdd * 100, 1),
           "total_return_pct": round(float((eq[-1] - 1) * 100), 1),
           "nifty_3y_return_pct": round(nifty * 100, 1) if nifty is not None else None,
           "cost_assumption_pct": COST * 100,
           "method": "Entry at next-session open; ATR stop/target; 15-day time-stop; 0.4% round-trip cost.",
           "verdict": None}
    if nifty is not None:
        beats = out["total_return_pct"] > nifty * 100
        out["verdict"] = ("The rule's cumulative return beats buy-and-hold Nifty over this span."
                          if beats else "The rule does NOT beat buy-and-hold Nifty over this span — treat Trading signals with caution.")
    try:
        CACHE_BT.write_text(json.dumps(out), encoding="utf-8")
    except Exception:
        pass
    (OUT / "backtest.json").write_text(json.dumps(out), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    print(json.dumps(run(now, max_age_days=0, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None), indent=2))
