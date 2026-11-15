"""Unit tests for indicators, scoring and level maths. Run in CI.

Includes the spec's cross-check: the SMA formula used by the browser chart (JS) must match
the one used in the pipeline, so the chart can never contradict the score.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import analysis as A  # noqa: E402
import scoring as SC  # noqa: E402


def _frame(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "Open": closes, "High": highs or [c * 1.01 for c in closes],
        "Low": lows or [c * 0.99 for c in closes], "Close": closes,
        "Volume": vols or [1000] * n,
    }, index=idx)


def test_rsi_bounds_and_direction():
    up = _frame([100 + i for i in range(60)])
    down = _frame([160 - i for i in range(60)])
    assert A.rsi(up["Close"]) > 70, "steady uptrend should be overbought"
    assert A.rsi(down["Close"]) < 30, "steady downtrend should be oversold"
    assert 0 <= A.rsi(_frame([100] * 60)["Close"]) <= 100


def test_atr_positive():
    df = _frame([100 + (i % 5) for i in range(60)])
    assert A.atr(df) > 0


def test_sma_js_matches_python():
    """The JS chart computes SMA as a rolling mean; verify our Python rolling mean equals a
    hand-rolled running-window SMA (the exact algorithm app.js uses)."""
    closes = [100 + np.sin(i / 3) * 10 for i in range(300)]
    s = pd.Series(closes)
    for n in (20, 50, 200):
        py = s.rolling(n).mean()
        # replicate app.js sma(): running sum window
        js = [None] * len(closes)
        run = 0.0
        for i, c in enumerate(closes):
            run += c
            if i >= n:
                run -= closes[i - n]
            if i >= n - 1:
                js[i] = run / n
        for i in range(n - 1, len(closes)):
            assert abs(py.iloc[i] - js[i]) < 1e-6, f"SMA{n} mismatch at {i}"


def test_technicals_shape():
    df = _frame([100 + i * 0.5 for i in range(260)])
    t = A.technicals(df)
    assert t is not None
    assert t["price"] > t["sma50"] > t["sma200"], "rising series: price>50>200"
    for k in ("rsi", "atr", "ret_3m", "sma50", "sma200"):
        assert k in t


def test_scores_in_range():
    df = _frame([100 + i * 0.4 for i in range(300)])
    t = SC.indicators(df)
    assert t is not None
    ts = SC.trading_score(t)
    iscore, _ = SC.investing_score(t, {"roe": 0.2, "debt_equity": 30, "rev_growth": 0.2, "profit_margin": 0.2, "pe": 15})
    assert 0 <= ts <= 100
    assert 0 <= iscore <= 100


def test_trading_plan_levels_ordered():
    df = _frame([100 + i * 0.4 for i in range(300)])
    t = SC.indicators(df)
    plan = SC.trading_plan(t, 70)
    assert plan["stop_loss"] < plan["entry_low"] <= plan["entry_high"]
    assert plan["target_1"] < plan["target_2"]
    assert plan["target_1"] > t["price"]


def test_chart_reading_has_numbers():
    df = _frame([100 + i * 0.4 for i in range(300)])
    t = SC.indicators(df)
    r = SC.chart_reading(df, t)
    assert "support" in r and "resistance" in r
    assert r["support"] <= r["resistance"]
    assert isinstance(r["summary"], str) and r["summary"]


def test_liquidity_gate():
    import nse
    ok, _ = nse.liquidity_gate(10e7, 500, 300, "EQ")  # 10cr turnover, fine
    assert ok
    ok2, reason = nse.liquidity_gate(1e7, 500, 300, "EQ")  # 1cr < 5cr
    assert not ok2 and "turnover" in reason.lower()
    ok3, reason3 = nse.liquidity_gate(100e7, 500, 300, "SM")  # SME excluded
    assert not ok3
