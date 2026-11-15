"""Dual scoring (Trading vs Investing), buy-at-market verdicts, and rule-based chart reading.

Trading = swing (days-weeks): trend + momentum + volume/delivery surge, ATR stop/targets, time-stop.
Investing = months-years: quality + valuation first, trend only as a timing filter, thesis + review date.
Everything is a computed rule with numbers shown; no free-text guessing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import analysis as A


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def indicators(df: pd.DataFrame) -> dict | None:
    """Core indicators from a stored OHLC frame (DatetimeIndex)."""
    t = A.technicals(df)
    if not t:
        return None
    c = df["Close"]
    vol = df["Volume"]
    t["vol20"] = float(vol.tail(20).mean()) if len(vol) >= 20 else float(vol.mean())
    t["vol_surge"] = float(vol.iloc[-1] / t["vol20"]) if t["vol20"] else 1.0
    t["sma20"] = float(c.rolling(20).mean().iloc[-1]) if len(c) >= 20 else float("nan")
    t["ema21"] = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    t["macd"] = float(macd.iloc[-1]); t["macd_signal"] = float(sig.iloc[-1])
    t["macd_hist"] = float(macd.iloc[-1] - sig.iloc[-1])
    # Bollinger width (squeeze/expansion)
    if len(c) >= 20:
        sd = c.rolling(20).std().iloc[-1]
        t["bb_width"] = float(4 * sd / t["sma20"]) if t["sma20"] else None
    else:
        t["bb_width"] = None
    t["days"] = int(len(c))
    t["day_change"] = (t["price"] / t["prev_close"] - 1) if t.get("prev_close") else None
    t["deliv_pct"] = float(df["deliv_pct"].dropna().iloc[-1]) if "deliv_pct" in df and df["deliv_pct"].notna().any() else None
    return t


def trading_score(t: dict) -> float:
    """0-100 swing score."""
    s = 0.0
    p, s20, s50, s200 = t["price"], t.get("sma20", float("nan")), t["sma50"], t["sma200"]
    s += 14 if p > s50 else 0
    s += 8 if (not np.isnan(s200) and p > s200) else 0
    s += 8 if (not np.isnan(s20) and p > s20) else 0
    s += _clip((t["ret_1m"] or 0) * 100 / 12, 0, 1) * 15
    s += _clip((t["ret_3m"] or 0) * 100 / 25, 0, 1) * 15
    r = t["rsi"]
    s += 10 if 50 <= r <= 68 else 6 if 45 <= r < 50 or 68 < r <= 74 else 2
    s += 8 if t["macd_hist"] > 0 else 0
    s += _clip((t.get("vol_surge", 1) - 1) / 1.0, 0, 1) * 12  # volume expansion
    dp = t.get("deliv_pct")
    s += 5 if (dp is not None and dp >= 50) else 2 if dp is not None else 0
    s += _clip(1 + (t["from_52w_high"] or -1) / 0.15, 0, 1) * 5
    return round(s, 1)


def investing_score(t: dict, f: dict | None) -> tuple[float, bool]:
    """0-100 quality+valuation first; trend as timing filter. Returns (score, had_fundamentals)."""
    qual, have = 0.0, 0
    if f:
        pe, roe, de, gr, pm = f.get("pe"), f.get("roe"), f.get("debt_equity"), f.get("rev_growth"), f.get("profit_margin")
        if roe is not None:
            have += 1; qual += 16 if roe > 0.18 else 10 if roe > 0.12 else 4 if roe > 0.06 else 0
        if de is not None:
            have += 1; qual += 12 if de < 50 else 7 if de < 120 else 0
        if gr is not None:
            have += 1; qual += 12 if gr > 0.15 else 8 if gr > 0.08 else 3 if gr > 0 else 0
        if pm is not None:
            have += 1; qual += 8 if pm > 0.15 else 4 if pm > 0.07 else 0
        if pe is not None and pe > 0:
            have += 1; qual += 12 if pe < 18 else 8 if pe < 28 else 4 if pe < 45 else 0
    if have == 0:
        qual = 30.0  # neutral when no fundamentals
    else:
        qual = qual / _invest_max(f) * 60
    # timing filter (40): long-term trend + not overbought + reasonable drawdown from high
    p, s200, s50 = t["price"], t["sma200"], t["sma50"]
    tim = 0.0
    tim += 16 if (not np.isnan(s200) and p > s200) else 0
    tim += 10 if p > s50 else 0
    tim += 8 if (t["ret_1y"] or 0) > 0 else 0
    tim += 6 if 40 <= t["rsi"] <= 70 else 0
    return round(qual + tim, 1), have > 0


def _invest_max(f):
    m = 0.0
    if f.get("roe") is not None: m += 16
    if f.get("debt_equity") is not None: m += 12
    if f.get("rev_growth") is not None: m += 12
    if f.get("profit_margin") is not None: m += 8
    if f.get("pe") is not None and f["pe"] > 0: m += 12
    return m or 1.0


def trading_plan(t: dict, score: float) -> dict:
    """Swing levels + time-stop + buy-at-market verdict."""
    p, a = t["price"], t["atr"]
    s50, s200, r = t["sma50"], t["sma200"], t["rsi"]
    uptrend = p > s50 and (np.isnan(s200) or p > s200)
    entry_hi = round(p + 0.4 * a, 2)   # max chase price (slightly above last close)
    stop = round(p - 1.8 * a, 2)
    t1, t2 = round(p + 2.7 * a, 2), round(p + 4.5 * a, 2)
    rr = round((t1 - p) / (p - stop), 2) if p > stop else None
    # verdict for someone who buys at market next session
    ext = (p - s50) / s50 if s50 else 0  # how extended above 50DMA
    if not uptrend or score < 45:
        verdict, vclass = "AVOID / WAIT", "wait"
        buy_upto = None
    elif r > 76 or ext > 0.18:
        verdict, vclass = f"TOO EXTENDED — wait for a dip to ~Rs {round(p - 0.8 * a):,}", "wait"
        buy_upto = round(p - 0.8 * a, 2)
    elif score >= 62:
        verdict, vclass = "BUY NOW AT MARKET", "buy"
        buy_upto = entry_hi
    else:
        verdict, vclass = "BUY ON SMALL DIP", "dip"
        buy_upto = round(p, 2)
    return {
        "verdict": verdict, "verdict_class": vclass, "buy_upto": buy_upto,
        "entry_low": round(p - 0.8 * a, 2), "entry_high": entry_hi, "stop_loss": stop,
        "target_1": t1, "target_2": t2, "risk_reward": rr, "time_stop_days": 15,
        "gap_rule": f"If it opens above Rs {buy_upto:,.0f}, skip today." if buy_upto else "",
        "applies": "Signal is for the next session (data is end-of-day).",
    }


def investing_plan(t: dict, f: dict | None, score: float) -> dict:
    """Entry style (lump vs staggered), thesis-broken condition, review date."""
    p, s50, s200 = t["price"], t["sma50"], t["sma200"]
    above200 = (not np.isnan(s200)) and p > s200
    dist200 = (p / s200 - 1) if (not np.isnan(s200) and s200) else 0
    if score >= 62 and above200:
        verdict, vclass = "BUY NOW AT MARKET (quality + uptrend)", "buy"
    elif score >= 55:
        verdict, vclass = "ACCUMULATE ON DIPS", "dip"
    elif score >= 45:
        verdict, vclass = "WATCH — wait for a better price or confirmation", "wait"
    else:
        verdict, vclass = "AVOID for now", "wait"
    # staggered if extended above 200DMA, lump if near/below it
    if dist200 > 0.12:
        entry_style = "Stagger in 3 tranches (now / −5% / −10%) — it's well above its 200-day average."
    elif dist200 < -0.05:
        entry_style = "Reasonable lump-sum zone — near/below its 200-day average (confirm quality)."
    else:
        entry_style = "Stagger in 2 tranches (now / on a dip)."
    broken = f"Thesis broken if it closes below Rs {round(min(s200, p * 0.85)):,} or fundamentals deteriorate (ROE/growth fall, debt rises)."
    return {"verdict": verdict, "verdict_class": vclass, "entry_style": entry_style,
            "thesis_broken_if": broken, "review": "Review in ~90 days or at next results.",
            "applies": "Long-term view; price levels are guides, not tight stops."}


# ---------------- rule-based fundamental analysis (for investing) ----------------
def fundamental_analysis(f: dict | None) -> dict | None:
    """Plain-language verdict per fundamental dimension, each with its number. For the Investing view."""
    if not f:
        return None
    out, pos, neg = {}, 0, 0
    pe, roe, de, gr, pm, dy = f.get("pe"), f.get("roe"), f.get("debt_equity"), f.get("rev_growth"), f.get("profit_margin"), f.get("div_yield")
    if pe is not None and pe > 0:
        v = "cheap" if pe < 15 else "reasonable" if pe < 25 else "rich" if pe < 40 else "very expensive"
        out["Valuation"] = f"P/E {pe:.1f} — {v}"
        pos += v in ("cheap", "reasonable"); neg += v in ("rich", "very expensive")
    if roe is not None:
        v = "excellent" if roe > 0.2 else "good" if roe > 0.15 else "average" if roe > 0.1 else "weak"
        out["Profitability"] = f"ROE {roe * 100:.0f}% — {v}"
        pos += v in ("excellent", "good"); neg += v == "weak"
    if pm is not None:
        out["Margins"] = f"Net margin {pm * 100:.0f}% — " + ("healthy" if pm > 0.12 else "thin" if pm < 0.05 else "moderate")
        pos += pm > 0.12; neg += pm < 0.05
    if gr is not None:
        v = "strong" if gr > 0.15 else "steady" if gr > 0.07 else "slow" if gr > 0 else "shrinking"
        out["Growth"] = f"Revenue {gr * 100:+.0f}% — {v}"
        pos += v in ("strong", "steady"); neg += v == "shrinking"
    if de is not None:
        v = "low debt" if de < 50 else "moderate debt" if de < 120 else "high debt"
        out["Leverage"] = f"Debt/Equity {de:.0f} — {v}"
        pos += de < 50; neg += de >= 120
    if dy:
        out["Dividend"] = f"Yield {dy:.1f}%"
    verdict = "Strong fundamentals" if pos >= 3 and neg == 0 else "Weak fundamentals" if neg >= 2 else "Mixed fundamentals"
    out["_verdict"] = verdict
    return out


# ---------------- foundational risk metrics (vs Nifty 50) ----------------
def risk_metrics(closes, dates, nifty_ret: dict) -> dict:
    """Beta, alpha (annualised), R^2, annualised volatility vs the Nifty 50.
    closes/dates: the stock's daily close series; nifty_ret: {date -> daily return}."""
    sret = {}
    for i in range(1, len(closes)):
        c0, c1 = closes[i - 1], closes[i]
        if c0 and not np.isnan(c0) and not np.isnan(c1):
            sret[str(dates[i])] = c1 / c0 - 1
    common = [d for d in sret if d in nifty_ret]
    if len(common) < 120:
        return {}
    s = np.array([sret[d] for d in common]); m = np.array([nifty_ret[d] for d in common])
    var = float(m.var())
    out = {"vol_ann": round(float(s.std() * np.sqrt(252)), 3)}
    if var > 0:
        beta = float(np.cov(s, m)[0, 1] / var)
        out["beta"] = round(beta, 2)
        out["alpha_ann"] = round(float((s.mean() - beta * m.mean()) * 252), 3)
        corr = float(np.corrcoef(s, m)[0, 1])
        out["r_squared"] = round(corr ** 2, 2)
    # max drawdown over the window
    eq = np.cumprod(1 + s); peak = np.maximum.accumulate(eq)
    out["max_drawdown"] = round(float(((eq - peak) / peak).min()), 3)
    out["sample_days"] = len(common)
    return out


# ---------------- rule-based chart reading ----------------
def chart_reading(df: pd.DataFrame, t: dict, levels: dict | None = None) -> dict:
    """Plain-language, rule-derived reading. Every line carries its numbers."""
    c = df["Close"]
    p = t["price"]
    def trend(sma, label):
        if np.isnan(sma):
            return f"{label}: not enough history"
        d = (p / sma - 1) * 100
        word = "up" if p > sma else "down"
        return f"{label}: {word} — price Rs {p:,.0f} is {abs(d):.1f}% {'above' if p>sma else 'below'} the {label.split()[0]} average (Rs {sma:,.0f})"
    short = trend(t.get("sma20", float("nan")), "Short (20d)")
    med = trend(t["sma50"], "Medium (50d)")
    lng = trend(t["sma200"], "Long (200d)")
    # support/resistance from recent swing highs/lows
    win = c.tail(120)
    res = float(win.max()); sup = float(win.min())
    r = t["rsi"]
    mom = f"RSI {r:.0f} ({'overbought' if r>70 else 'oversold' if r<30 else 'neutral'}); MACD {'bullish' if t['macd_hist']>0 else 'bearish'} ({t['macd_hist']:+.1f})"
    dp = t.get("deliv_pct")
    vol = f"Volume {t.get('vol_surge',1):.1f}x its 20-day average" + (f", delivery {dp:.0f}%" if dp is not None else "")
    bbw = t.get("bb_width")
    vola = f"ATR {t['atr']/p*100:.1f}% of price" + (f"; Bollinger {'squeeze (low)' if bbw and bbw<0.08 else 'wide (volatile)' if bbw and bbw>0.2 else 'normal'}" if bbw else "")
    events = []
    if not np.isnan(t["sma50"]) and not np.isnan(t["sma200"]):
        if t["sma50"] > t["sma200"] and (c.rolling(50).mean().iloc[-6] <= c.rolling(200).mean().iloc[-6]):
            events.append("Golden cross (50d crossed above 200d) in the last week")
    if p >= float(c.tail(252).max()) * 0.999:
        events.append("At a 52-week high")
    if p <= float(c.tail(252).min()) * 1.001:
        events.append("At a 52-week low")
    if p > res * 0.995 and t.get("vol_surge", 1) > 1.3:
        events.append(f"Breaking out of its {len(win)}-day range (Rs {res:,.0f}) on higher volume")
    # one-line summary + what to watch
    if p > t["sma50"] and (np.isnan(t["sma200"]) or p > t["sma200"]):
        summary = "Uptrend across medium and long term."
        watch = f"A close above Rs {res:,.0f} extends it; below Rs {t['sma50']:,.0f} (50d) weakens it."
    elif p < t["sma50"] and (not np.isnan(t["sma200"]) and p < t["sma200"]):
        summary = "Downtrend — below both key averages."
        watch = f"A close above Rs {t['sma50']:,.0f} (50d) would be the first repair sign; support near Rs {sup:,.0f}."
    else:
        summary = "Mixed / transitional — signals conflict."
        watch = f"Resistance Rs {res:,.0f}, support Rs {sup:,.0f}; a decisive close either side sets direction."
    return {"short": short, "medium": med, "long": lng,
            "support": round(sup, 2), "resistance": round(res, 2),
            "momentum": mom, "volume": vol, "volatility": vola,
            "events": events, "summary": summary, "watch_next": watch}
