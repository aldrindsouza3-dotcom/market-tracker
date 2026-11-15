"""Phase 1b/2/3/5 builder: full eligible-universe dual scoring + per-symbol detail files + chart reading.

Called by run_daily. Isolated and defensive: any failure prints and returns without breaking the main run.
Writes:
  site/data/stocks/<SYMBOL>.json   per-symbol detail (compact OHLCV for charts, indicators, both scores,
                                   trading & investing plans, rule-based chart reading, fundamentals, links)
  site/data/stocks_index.json      eligible universe with both scores/signals/verdicts (for Trading/Investing tabs + screeners)
  site/data/modes.json             dual Top-5 (trading + investing) for the Today/mode tabs
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd

import nse
import scoring as SC
import store

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
STOCKS = OUT / "stocks"
FUND_CACHE = nse.CACHE / "fundamentals.json"

SEED_PER_RUN = 300      # new symbols to seed history for, per run (spreads Yahoo load; Actions cache persists)
FUND_PER_RUN = 90       # fundamentals refreshed per run (weekly cadence per symbol)
TOP_N = 1400            # cover all liquidity-gate-eligible stocks (grows to full coverage as history seeds)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _load_fund_cache() -> dict:
    try:
        return json.loads(FUND_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _refresh_fundamentals(symbols: list[str], cache: dict, now_iso: str, limit: int) -> None:
    import yfinance as yf
    stale = [s for s in symbols if (now_iso[:10] >
             (cache.get(s, {}).get("asof", "0000")[:10] if s in cache else "0000"))]
    # oldest first; cap per run
    stale.sort(key=lambda s: cache.get(s, {}).get("asof", ""))
    for s in stale[:limit]:
        try:
            i = yf.Ticker(f"{s}.NS").info or {}
            cache[s] = {"pe": i.get("trailingPE"), "fwd_pe": i.get("forwardPE"), "roe": i.get("returnOnEquity"),
                        "debt_equity": i.get("debtToEquity"), "rev_growth": i.get("revenueGrowth"),
                        "profit_margin": i.get("profitMargins"), "div_yield": i.get("dividendYield"),
                        "market_cap": i.get("marketCap"), "sector": i.get("sector"), "asof": now_iso}
        except Exception:
            pass
    try:
        FUND_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass


def _compact_ohlc(df: pd.DataFrame, max_rows: int = 1300) -> dict:
    d = df.tail(max_rows)
    r2 = lambda s: [None if pd.isna(x) else round(float(x), 2) for x in s]
    vint = lambda x: None if (pd.isna(x) or not pd.api.types.is_number(x)) else int(round(float(x)))
    return {"t": [str(x) for x in d["date"]], "o": r2(d["open"]), "h": r2(d["high"]),
            "l": r2(d["low"]), "c": r2(d["close"]), "v": [vint(x) for x in d["volume"]],
            "dp": [None if pd.isna(x) else round(float(x), 1) for x in d["deliv_pct"]] if "deliv_pct" in d else []}


def build(now: dt.datetime, universe_rows: list[dict] | None = None) -> dict | None:
    try:
        STOCKS.mkdir(parents=True, exist_ok=True)
        s = nse.session()
        recent = nse.recent_bhavcopies(22, s)
        if not recent:
            print("  ! stocks: no bhavcopy; skipping dual-mode build")
            return None
        asof, latest = recent[0]
        sec = nse.securities(s)
        uni = universe_rows or nse.build_universe(recent, sec)
        eligible = [u for u in uni if u["eligible"]][:TOP_N]
        elig_syms = [u["symbol"] for u in eligible]

        # 1) maintain history: seed new symbols (bounded), append today's bhav to all cached
        seeded = store.seed_from_yahoo(elig_syms, SEED_PER_RUN)
        added = store.append_bhav_day(latest)
        print(f"  history: seeded {seeded} new, appended today to {added} symbols")

        # 2) fundamentals (weekly cadence, bounded)
        fcache = _load_fund_cache()
        _refresh_fundamentals(elig_syms, fcache, now.isoformat(), FUND_PER_RUN)

        # Nifty 50 daily returns, for beta/alpha (fetched once per run)
        nifty_ret = {}
        try:
            import yfinance as yf
            nd = yf.download("^NSEI", period="3y", interval="1d", auto_adjust=True, progress=False)
            nc = nd["Close"]
            if hasattr(nc, "columns"):
                nc = nc.iloc[:, 0]
            nc = nc.dropna()
            prev = None
            for ts, v in nc.items():
                d = ts.date().isoformat()
                if prev:
                    nifty_ret[d] = float(v) / prev - 1
                prev = float(v)
        except Exception as ex:
            print("  ! nifty returns unavailable (beta/alpha skipped):", str(ex)[:80])

        # 3) score each eligible symbol that has history
        index_rows, scored = [], 0
        meta = {u["symbol"]: u for u in uni}
        for sym in elig_syms:
          try:
            h = store.load(sym)
            if h is None or len(h) < 60:
                continue
            ohlc = store.to_ohlc(h)
            t = SC.indicators(ohlc)
            if not t:
                continue
            f = fcache.get(sym)
            tscore = SC.trading_score(t)
            iscore, had_f = SC.investing_score(t, f)
            tplan = SC.trading_plan(t, tscore)
            iplan = SC.investing_plan(t, f, iscore)
            reading = SC.chart_reading(ohlc, t)
            risk = SC.risk_metrics(h["close"].tolist(), h["date"].tolist(), nifty_ret) if nifty_ret else {}
            u = meta.get(sym, {})
            row = {"symbol": sym, "name": u.get("name", sym), "sector": (f or {}).get("sector"),
                   "close": round(t["price"], 2), "day_change": t["day_change"],
                   "trading_score": tscore, "investing_score": iscore,
                   "trading_verdict": tplan["verdict_class"], "investing_verdict": iplan["verdict_class"],
                   "trading_verdict_txt": tplan["verdict"], "trading_buy_upto": tplan["buy_upto"],
                   "trading_stop": tplan["stop_loss"], "trading_t1": tplan["target_1"],
                   "investing_verdict_txt": iplan["verdict"],
                   "rsi": round(t["rsi"], 0), "ret_1y": t["ret_1y"], "ret_3m": t["ret_3m"], "days": t["days"],
                   "vol_surge": round(t.get("vol_surge", 1), 2), "risk_reward": tplan.get("risk_reward"),
                   "pe": (f or {}).get("pe"), "roe": (f or {}).get("roe"), "rev_growth": (f or {}).get("rev_growth"),
                   "med_turnover_cr": u.get("med_turnover_cr"), "has_fundamentals": had_f}
            index_rows.append(row)
            # per-symbol detail file
            detail = {"symbol": sym, "name": u.get("name", sym), "asof": asof.isoformat(),
                      "source": "NSE bhavcopy + Yahoo (history)", "eligible": True,
                      "price": round(t["price"], 2), "day_change": t["day_change"], "days_history": t["days"],
                      "indicators": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()},
                      "trading": {"score": tscore, **tplan}, "investing": {"score": iscore, "has_fundamentals": had_f, **iplan},
                      "reading": reading, "risk": risk, "fundamentals": f,
                      "links": {"tickertape": u.get("tickertape"), "screener": u.get("screener"), "moneycontrol": u.get("moneycontrol")},
                      "ohlc": _compact_ohlc(h),
                      "disclaimer": "Research aid, not investment advice. End-of-day data."}
            (STOCKS / f"{sym}.json").write_text(json.dumps(_clean(detail)), encoding="utf-8")
            scored += 1
          except Exception as _ex:
            print(f"  . skip {sym}: {str(_ex)[:80]}")
            continue

        (OUT / "stocks_index.json").write_text(json.dumps(_clean({
            "generated_at": now.isoformat(), "asof": asof.isoformat(), "count": len(index_rows),
            "universe_total": len(uni), "eligible_total": sum(1 for u in uni if u["eligible"]),
            "note": f"Top {TOP_N} most-liquid eligible stocks scored in full; more each run as history seeds.",
            "rows": index_rows})), encoding="utf-8")

        # 4) dual Top-5 (diversified by sector where possible)
        def top5(key, verdict_key):
            cand = [r for r in index_rows if r[verdict_key] in ("buy", "dip")]
            cand.sort(key=lambda r: -r[key])
            out, seen = [], set()
            for r in cand:
                sec_k = r.get("sector") or r["symbol"]
                if sec_k in seen and len(out) < 5:
                    continue
                seen.add(sec_k); out.append(r)
                if len(out) >= 5:
                    break
            if len(out) < 5:
                out += [r for r in cand if r not in out][:5 - len(out)]
            return out[:5]

        modes = {"generated_at": now.isoformat(), "asof": asof.isoformat(),
                 "trading_top5": top5("trading_score", "trading_verdict"),
                 "investing_top5": top5("investing_score", "investing_verdict"),
                 "scored": scored}
        (OUT / "modes.json").write_text(json.dumps(_clean(modes), encoding="utf-8" and None) if False else json.dumps(_clean(modes)), encoding="utf-8")
        print(f"  dual-mode: scored {scored} stocks; trading & investing Top-5 written")
        return modes
    except Exception as ex:
        import traceback
        print("  ! build_stocks failed (non-fatal):", str(ex)[:160])
        traceback.print_exc()
        return None
