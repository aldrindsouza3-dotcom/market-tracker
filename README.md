<div align="center">

# 📈 Market Tracker

**A free, self-updating market dashboard for Indian investors — with a global view.**

It scores stocks, mutual funds, gold, silver and more every weekday, picks a daily **Top 5**,
and pushes it straight to your phone. Installable on Android like a real app. Runs in the cloud with your PC off.

🔗 **Live app:** https://aldrindsouza3-dotcom.github.io/market-tracker/

</div>

> [!IMPORTANT]
> This is a **research aid, not investment advice**, and the author is not a SEBI-registered adviser.
> All data is **end-of-day and delayed**. Verify every idea yourself before investing. You use it at your own risk.

---

## ✨ What it does

| | |
|---|---|
| 🇮🇳 **India first** | Nifty 50 + 40 midcaps (89 stocks), Indian mutual funds, IPOs, USD/INR |
| 🌍 **Global context** | S&P 500, NASDAQ, FTSE (UK), Nikkei (Japan), Shanghai & Hang Seng (China), DAX, KOSPI |
| 🥇 **Metals & commodities** | Gold, silver, copper, platinum, crude oil, natural gas, rare-earth proxies |
| 💱 **Currency & rates** | Rupee vs USD/EUR/GBP/JPY/CNY, US Treasury yields, dollar index |
| ⭐ **Daily Top 5** | Best ideas across stocks, metals and funds — with buy zone, stop-loss & targets |
| 📲 **Phone alerts** | Pushed to your installed app twice a day, automatically |
| 📊 **Analytics** | Market regime, breadth, sector heat, advancers/decliners, top movers, trend charts |
| 🧾 **Track record** | Every past pick is logged and marked to market, so you can judge the rules honestly |

---

## 📱 Install it on your phone (Android)

1. Open the **live link** above in **Chrome**.
2. Tap **Install app** (or Chrome menu → *Add to Home screen*).
3. Open it from your home screen — it runs full-screen, like a native app, and works offline.

Then tap **Turn on alerts** once to receive the daily Top 5 inside the app. No Play Store, no cost.

---

## 🧠 How it works

```
 Yahoo Finance ─┐
 AMFI / mfapi  ─┤   GitHub Actions          GitHub Pages            Your phone
 investorgain  ─┼─▶ (runs 9:15 & 17:00 ─▶   (hosts the app  ─▶      (installed app
 Google News   ─┘    IST, Mon–Fri)          + daily data)           shows Top 5)
```

1. **Fetch** — end-of-day prices (Yahoo Finance), mutual-fund NAVs (AMFI via mfapi.in), IPOs (investorgain.com) and news headlines. All free, no paid API.
2. **Score (0–100)** — each asset gets:
   - **Trend** — price vs its 50- and 200-day moving averages
   - **Momentum** — 3-month and 6-month returns
   - **RSI** sanity check + distance from its 52-week high
   - **Fundamentals** (stocks) — P/E, ROE, debt/equity, revenue growth, margin
3. **Signal & levels** — a **BUY / HOLD / SELL** call, plus an entry zone, stop-loss and two targets sized from volatility (ATR) for a defined risk-reward.
4. **Market regime** — **RISK-ON / MIXED / RISK-OFF**, from the Nifty's trend and how many stocks sit above their 200-day average. New buys are suppressed in RISK-OFF.
5. **Top 5** — the strongest, diversified BUY ideas are chosen and pushed to your phone.
6. **Track record** — picks are logged with their levels and checked daily against stop/target, building an honest hit-rate over time.

---

## 🗂️ The app's tabs

- **Today** — market regime + the daily Top 5 cards
- **Overview** — breadth gauge, advancers vs decliners, sector performance, top movers, index/metal/FX snapshot, trend sparklines
- **India stocks** — all 89, sortable; tap a row for levels + fundamentals
- **Mutual funds** — ranked by 3-yr CAGR, risk-adjusted return and drawdown
- **Gold, silver & commodities** · **Currency & bonds** · **Global markets**
- **IPOs** — live list with price, dates, subscription and grey-market premium
- **Track record** · **News** · **How it works**

---

## 🛠️ Run it locally

```bash
pip install -r requirements.txt
python pipeline/run_daily.py --no-notify      # full run ~75s (add --fast to skip fundamentals/funds)
python -m http.server 8765 --directory site   # then open http://localhost:8765
```

## ☁️ Deploy your own (free, runs with your PC off)

1. Push this folder to a **public** GitHub repo.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Actions → Daily market run → Run workflow.** The deploy step prints your live URL.
4. **Settings → Secrets and variables → Actions → Variables:** add `SITE_URL` = that URL.

The job then runs automatically on weekdays at **09:15** and **17:00 IST**.

---

## 🔔 Notification channels

Add the matching GitHub **secrets**; any channel you don't configure is simply skipped.

| Channel | Secrets | Notes |
|---|---|---|
| **In-app push** (recommended) | `VAPID_PRIVATE_KEY`, `PUSH_SUBS` | Your installed app shows the alert itself. Tap *Turn on alerts* in the app to generate `PUSH_SUBS`. No third-party app. |
| **ntfy** | `NTFY_TOPIC` | Free push via the ntfy app; subscribe to a long, secret topic name. |
| **Telegram** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Create a bot with @BotFather. |
| **WhatsApp** | `WA_TOKEN`, `WA_PHONE_ID`, `WA_TO`, `WA_TEMPLATE` | Meta WhatsApp Cloud API — needs a developer app and an approved template. |
| **Email** | `SMTP_USER`, `SMTP_PASS`, `MAIL_TO` | Gmail app password. |

> Keep `VAPID_PRIVATE_KEY` private (it's in `.gitignore`, never committed). The public key lives in the app and is safe to share.

---

## ⚙️ Customise

- **What's tracked** — edit the lists in [`pipeline/universe.py`](pipeline/universe.py) (stocks, midcaps, funds, commodities, currencies).
- **Scoring & signals** — tune the rules in [`pipeline/analysis.py`](pipeline/analysis.py).
- **Schedule** — change the cron times in [`.github/workflows/daily.yml`](.github/workflows/daily.yml).

## 📁 Project layout

```
market-tracker/
├─ pipeline/
│  ├─ run_daily.py   # orchestrates the daily run and writes site/data/*.json
│  ├─ data.py        # fetchers: prices, fundamentals, fund NAVs, IPOs, news
│  ├─ analysis.py    # indicators, 0–100 scoring, trade levels, regime
│  ├─ notify.py      # push to in-app / ntfy / Telegram / WhatsApp / email
│  └─ universe.py    # the tracked lists — edit freely
├─ site/             # the installable dashboard (PWA) + generated data
└─ .github/workflows/daily.yml   # the cloud schedule
```

---

## ⚠️ Known limits

- Prices are **end-of-day**, not real-time — good for daily investing, not intraday trading.
- Scoring rules are **generic**; taxes (STCG/LTCG), brokerage and slippage are not modelled.
- **IPO** data is unofficial (investorgain.com); if it breaks, the tab links to NSE/Chittorgarh.
- No free feed exists for the **India 10Y G-Sec yield**, rare-earth spot prices, or real-time quotes.
- On phones, Android battery-savers can occasionally pause web notifications — re-enable in the app if alerts go quiet.

---

## 🔒 Data & privacy

Runs entirely on free, public data sources and your own GitHub account. No brokerage login, no trading, no personal
financial data. Notification keys live only in GitHub's encrypted secrets.

## 📄 Licence & data

Built for personal use. Market data belongs to its providers (Yahoo Finance, AMFI, investorgain.com) and is subject to their terms. Not affiliated with NSE, BSE or any of them.
