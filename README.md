# Market Tracker (India first)

Daily job scores the Nifty-50, Indian mutual funds, gold/silver/commodities, currencies vs INR, bond yields and
global indices (US, UK, Japan, China, Germany, Korea), writes `site/data/latest.json`, logs the top picks to
`site/data/track_record.json`, and pushes a Top-5 message to your phone. `site/` is a static dashboard.

Research aid only, not investment advice. Data is end-of-day and delayed.

## Run locally
    pip install -r requirements.txt
    python pipeline/run_daily.py --no-notify     # ~75 s; add --fast to skip fundamentals/funds
    python -m http.server 8765 --directory site  # open http://localhost:8765

## Free cloud hosting (runs with your PC off)
1. Create a GitHub repo and push this folder as the repo root.
2. Settings > Pages > Source: **GitHub Actions**.
3. Actions tab > "Daily market run" > Run workflow. Your dashboard URL appears in the deploy step.
4. Settings > Secrets and variables > Actions > Variables: add `SITE_URL` = that URL (it is linked in notifications).
5. Add secrets for the notification channel(s) you want (see below). Runs weekdays 09:15 and 17:00 IST.

## Phone notifications (add secrets; unset channels are skipped)
| Channel | Secrets | Notes |
|---|---|---|
| **ntfy (easiest)** | `NTFY_TOPIC` | Install the ntfy app, subscribe to a long random topic name, use the same value. Free, instant push. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Create a bot with @BotFather. |
| WhatsApp | `WA_TOKEN`, `WA_PHONE_ID`, `WA_TO`, `WA_TEMPLATE` | Meta WhatsApp Cloud API: needs a Meta developer app, a test/business number and an approved message template with one body variable. Free tier covers low volume. |
| Email | `SMTP_USER`, `SMTP_PASS`, `MAIL_TO` | Gmail app password. |

## Tune it
`pipeline/universe.py` lists every stock, fund search term, commodity and currency. Scoring rules are in
`pipeline/analysis.py`; check the Track record tab before trusting them with real money.

## Known gaps
- IPO list comes from investorgain.com (unofficial, includes grey-market premium); if it breaks the tab shows NSE/Chittorgarh links.
- Screens the Nifty-50 plus 40 midcaps; extend `MIDCAPS` in `universe.py` for more.
- Indian 10Y G-Sec yield, rare-earth spot prices and real-time prices have no free feed.
