<div align="center">

# 📈 Market Tracker

**A free, self-updating market platform for Indian investors — with a global view.**

Scores the whole NSE market every weekday, splits ideas into **Trading** and **Investing**, gives a plain
**buy-at-market verdict** for each, draws an **interactive chart** with a rule-based reading, and pushes a daily
**Top 5** to your phone. Installable on Android. Runs in the cloud with your PC off.

🔗 **Live app:** https://aldrindsouza3-dotcom.github.io/market-tracker/

</div>

> [!IMPORTANT]
> **Research aid, not investment advice.** The author is not a SEBI-registered adviser. Data is **end-of-day and
> delayed**. The built-in **Backtest** tab shows, honestly, whether the Trading rule actually beats holding the Nifty —
> read it before trusting any signal. Verify everything yourself. You use this at your own risk.

---

## ✨ What it does

| Area | Detail |
|---|---|
| 🔎 **Whole market** | Every NSE equity (~3,400) searchable; a **liquidity gate** marks ~1,100 as eligible for picks, the rest labelled with the reason. |
| ⚡ **Trading mode** | Swing (days–weeks): trend + momentum + volume/delivery. Buy-up-to price, stop-loss, two targets, risk-reward, time-stop. |
| ◈ **Investing mode** | Long-term (months–years): quality & valuation first, trend as timing. Staggered-entry plan, thesis-broken condition, review date. |
| 🟢 **Buy-at-market verdict** | Each pick answers *“can I buy now, up to what price?”* — plus a gap rule and a note that the signal is for the next session. |
| 📊 **Interactive charts** | Candlestick/line, volume, SMAs, Bollinger, entry/stop/target overlays, zoom/pan/crosshair, 1M→Max ranges — bundled offline (TradingView Lightweight Charts, Apache-2.0). |
| 📝 **Chart reading** | Rule-based, numbers shown: trend on 3 horizons, support/resistance, momentum, volume/delivery, volatility, detected events, “watch next”. |
| 🧮 **Position sizer** | Enter capital + risk %; get share quantity and rupee risk. Saved on your device. |
| ⭐ **Watchlist** | Save stocks on your device; one tap from any stock page. |
| 🧪 **Backtest** | The Trading rule tested over stored history vs buy-and-hold Nifty, with a cost assumption. Says so if it doesn’t beat the index. |
| 🌍 **Global + metals + FX** | S&P 500, NASDAQ, FTSE, Nikkei, China, etc.; gold, silver, commodities; rupee pairs and yields. |
| 💰 **Funds, IPOs, news** | Indian mutual funds ranked; live IPO list with GMP; impact-ranked headlines. |
| 📲 **Daily phone push** | Top 5 to your installed app (web push) and/or ntfy, twice a day. |
| ✅ **Data-quality badge** | Flags stale data or absurd (unadjusted) moves in the header. |

---

## 📱 Install on Android
Open the live link in **Chrome → Install app** (or *Add to Home screen*). It runs full-screen, works offline, and
shows the daily alert itself. Bottom navigation: **Today · Trading · Investing · Markets · More**.

---

## 🧠 How it works
```
NSE bhavcopy (whole market, delivery%) ─┐
Yahoo (history seed, indices, FX, funds)├─▶ GitHub Actions (09:15 & 17:00 IST) ─▶ GitHub Pages ─▶ your phone
AMFI/mfapi (fund NAVs) · investorgain   ─┘        scores · charts · backtest          app + data      (web push)
```
1. **One NSE bhavcopy** covers the whole market daily (prices + delivery %), with **BSE** and **last-good cache** fallbacks.
2. Per-symbol **history** is seeded once from Yahoo (split/bonus-adjusted) and maintained daily from the bhavcopy. Stored in a **GitHub Actions cache**, not committed — so the repo never bloats.
3. Each eligible stock gets a **Trading** and an **Investing** score, a verdict, levels, and a chart reading — all from computed rules with the numbers shown.
4. Two **Top-5** lists are chosen and pushed to your phone. The **Backtest** validates the Trading rule against the Nifty.

---

## 🗂️ Tabs
**Today · Trading · Investing · Overview · All stocks (search) · Watchlist · India stocks · Mutual funds ·
Commodities · Currency & bonds · Global · IPOs · Track record · Backtest · News · How it works.**
Tap any stock anywhere to open its **detail page** (chart + reading + both scores + fundamentals + position sizer + deep links).

---

## 🛠️ Run locally
```bash
pip install -r requirements.txt
python pipeline/run_daily.py --no-notify      # add --fast to skip heavy steps
python -m pytest tests/ -q                     # indicator / scoring tests
python -m http.server 8765 --directory site    # open http://localhost:8765
```

## ☁️ Deploy your own (free)
Push to a **public** repo → **Settings → Pages → GitHub Actions** → run the **Daily market run** workflow once.
Set the `SITE_URL` variable to your Pages URL. Runs weekdays 09:15 & 17:00 IST. Tests run in CI on every push.

## 🔔 Notifications (add GitHub secrets; unset channels are skipped)
| Channel | Secrets |
|---|---|
| **In-app web push** | `VAPID_PRIVATE_KEY`, `PUSH_SUBS` (tap *Turn on alerts* in the app to generate) |
| ntfy | `NTFY_TOPIC` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| WhatsApp | `WA_TOKEN`, `WA_PHONE_ID`, `WA_TO`, `WA_TEMPLATE` |
| Email | `SMTP_USER`, `SMTP_PASS`, `MAIL_TO` |

## 📁 Layout
```
pipeline/  nse.py (market data) · store.py (history) · analysis.py + scoring.py (indicators/scores)
           build_stocks.py (dual scoring + per-symbol files) · backtest.py · run_daily.py · notify.py
site/      app.js · index.html · style.css · sw.js · vendor/lightweight-charts.js · data/ (generated)
tests/     indicator & scoring unit tests (run in CI)
```

## ⚙️ Data sources
NSE bhavcopy & securities list (prices, delivery %), BSE bhavcopy (fallback), Yahoo Finance (history seed, global
indices, commodities, FX, fundamentals), AMFI via mfapi.in (fund NAVs), investorgain.com (IPOs, unofficial),
Google News RSS (headlines). No paid APIs. No scraping of Tickertape/Moneycontrol/Screener — those are deep links only.

## ⚠️ Limits & what’s still deepening
- Scoring currently covers the **top ~450 most-liquid** eligible stocks (expands each run as history seeds); all ~3,400 are searchable.
- **Charts:** daily candles with SMAs, Bollinger and overlays. Still to add: EMA/Supertrend/Ichimoku/VWAP, separate RSI/MACD panes, weekly/monthly candle aggregation, drawing tools, compare mode, pick/dividend markers.
- **Corporate actions:** history seeded from Yahoo is split/bonus-adjusted; bhavcopy-appended days are raw (minor until the next re-seed).
- Not yet added: FII/DII flows, bulk/block deals, a dedicated event screener tab, per-mode forward track record, earnings-calendar alerts.
- End-of-day data only — good for daily investing, not intraday. Taxes, full brokerage and slippage beyond the backtest’s assumption are not modelled.
- No free feed for India 10Y G-Sec yield, rare-earth spot prices, or real-time quotes.
