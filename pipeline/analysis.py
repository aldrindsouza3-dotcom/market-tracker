"""Indicators, scoring and trade-level rules. Pure functions, no network."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def atr(df: pd.DataFrame, n: int = 14) -> float:
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def technicals(df: pd.DataFrame) -> dict | None:
    """df: daily OHLCV with >= ~210 rows."""
    df = df.dropna(subset=["Close"])
    if len(df) < 120:
        return None
    c = df["Close"]
    last = float(c.iloc[-1])
    sma50 = float(c.rolling(50).mean().iloc[-1])
    sma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else float("nan")
    ret = lambda d: float(last / c.iloc[-d - 1] - 1) if len(c) > d else float("nan")
    hi52 = float(c.tail(252).max())
    return {
        "price": last, "sma50": sma50, "sma200": sma200, "rsi": rsi(c), "atr": atr(df),
        "ret_1m": ret(21), "ret_3m": ret(63), "ret_6m": ret(126), "ret_1y": ret(252) if len(c) > 252 else float("nan"),
        "from_52w_high": last / hi52 - 1, "vol_ann": float(c.pct_change().tail(126).std() * np.sqrt(252)),
        "prev_close": float(c.iloc[-2]), "asof": str(df.index[-1].date()),
    }


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def technical_score(t: dict) -> float:
    """0-70: trend (30) + momentum (25) + RSI sanity (10) + closeness to 52w high (5)."""
    s = 0.0
    p, s50, s200 = t["price"], t["sma50"], t["sma200"]
    s += 10 if p > s50 else 0
    s += 10 if (not np.isnan(s200) and p > s200) else 0
    s += 10 if (not np.isnan(s200) and s50 > s200) else 0
    s += _clip(t["ret_3m"] * 100 / 20, 0, 1) * 12
    s += _clip((t["ret_6m"] if not np.isnan(t["ret_6m"]) else 0) * 100 / 30, 0, 1) * 13
    r = t["rsi"]
    s += 10 if 45 <= r <= 68 else 5 if 38 <= r < 45 or 68 < r <= 74 else 0
    s += _clip(1 + t["from_52w_high"] / 0.25, 0, 1) * 5
    return s


def fundamental_score(f: dict | None) -> tuple[float, bool]:
    """0-30 from valuation/quality; returns (score, had_data). Missing data -> neutral 15."""
    if not f:
        return 15.0, False
    pts, have = 0.0, 0
    pe, roe, de, gr, pm = f.get("pe"), f.get("roe"), f.get("debt_equity"), f.get("rev_growth"), f.get("profit_margin")
    if pe is not None and pe > 0:
        have += 1; pts += 7 if pe < 20 else 5 if pe < 30 else 3 if pe < 45 else 0
    if roe is not None:
        have += 1; pts += 8 if roe > 0.18 else 5 if roe > 0.12 else 2 if roe > 0.06 else 0
    if de is not None:
        have += 1; pts += 5 if de < 50 else 3 if de < 120 else 0
    if gr is not None:
        have += 1; pts += 6 if gr > 0.15 else 4 if gr > 0.07 else 1 if gr > 0 else 0
    if pm is not None:
        have += 1; pts += 4 if pm > 0.15 else 2 if pm > 0.07 else 0
    if have == 0:
        return 15.0, False
    return pts * 30 / _max_possible(f), True


def _max_possible(f: dict) -> float:
    m = 0.0
    if f.get("pe") is not None and f["pe"] > 0: m += 7
    if f.get("roe") is not None: m += 8
    if f.get("debt_equity") is not None: m += 5
    if f.get("rev_growth") is not None: m += 6
    if f.get("profit_margin") is not None: m += 4
    return m or 1.0


def trade_plan(t: dict, score: float) -> dict:
    """Rule-based signal and levels. Not a prediction: levels follow trend + volatility (ATR)."""
    p, a = t["price"], t["atr"]
    s50, s200, r = t["sma50"], t["sma200"], t["rsi"]
    uptrend = p > s50 and (np.isnan(s200) or p > s200)
    if p < s50 and (not np.isnan(s200) and p < s200):
        signal, why = "SELL / AVOID", "Below both 50- and 200-day averages (downtrend)"
    elif r > 76:
        signal, why = "HOLD - DON'T CHASE", f"Overbought (RSI {r:.0f}); wait for a pullback"
    elif uptrend and score >= 62:
        signal, why = "BUY", "Uptrend with strong score; buy in the entry zone"
    elif uptrend:
        signal, why = "HOLD / ACCUMULATE", "Uptrend but score only moderate; add on dips"
    else:
        signal, why = "WAIT", "Trend not confirmed yet"
    entry_lo, entry_hi = p - 1.0 * a, p
    return {
        "signal": signal, "reason": why,
        "entry_low": round(entry_lo, 2), "entry_high": round(entry_hi, 2),
        "stop_loss": round(p - 2.0 * a, 2), "target_1": round(p + 3.0 * a, 2), "target_2": round(p + 5.0 * a, 2),
        "trail_rule": "Exit if it closes below the stop, or below the 50-day average after reaching Target 1",
    }


def mf_metrics(nav: pd.Series) -> dict | None:
    """nav: Series indexed by date, ascending."""
    nav = nav.dropna()
    if len(nav) < 260:
        return None
    last = float(nav.iloc[-1])
    cagr = lambda yrs: float((last / nav.iloc[-int(252 * yrs) - 1]) ** (1 / yrs) - 1) if len(nav) > int(252 * yrs) else None
    r = nav.pct_change().dropna().tail(756)
    dd = float((nav.tail(756) / nav.tail(756).cummax() - 1).min())
    vol = float(r.std() * np.sqrt(252))
    return {"nav": last, "asof": str(nav.index[-1].date()), "ret_1y": cagr(1), "cagr_3y": cagr(3), "cagr_5y": cagr(5),
            "vol": vol, "max_drawdown": dd,
            "sharpe_like": (cagr(3) or cagr(1) or 0) / vol if vol else 0}


def mf_score(m: dict) -> float:
    base = m["cagr_3y"] if m["cagr_3y"] is not None else m["ret_1y"] or 0
    return round(_clip(base / 0.25, 0, 1) * 45 + _clip(m["sharpe_like"] / 1.5, 0, 1) * 30
                 + _clip(1 + m["max_drawdown"] / 0.4, 0, 1) * 25, 1)
