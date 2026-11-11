"""Daily push. Configure any of these via environment variables / GitHub secrets; unset channels are skipped.

Phone push (easiest, free):  NTFY_TOPIC            -> install the ntfy app, subscribe to your secret topic
Telegram:                    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
WhatsApp (Meta Cloud API):   WA_TOKEN + WA_PHONE_ID + WA_TO (+ optional WA_TEMPLATE)
Email:                       SMTP_USER + SMTP_PASS (+ MAIL_TO)  (Gmail app password)
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import requests


def send_all(title: str, body: str, url: str | None = None) -> list[str]:
    sent = []
    e = os.environ.get
    if e("NTFY_TOPIC"):
        try:
            h = {"Title": title.encode("utf-8")[:250].decode("utf-8", "ignore"), "Priority": "default"}
            if url:
                h["Click"] = url
            requests.post(f"https://ntfy.sh/{e('NTFY_TOPIC')}", data=body.encode("utf-8"), headers=h, timeout=20).raise_for_status()
            sent.append("ntfy")
        except Exception as ex:
            print("  ! ntfy failed:", ex)
    if e("TELEGRAM_BOT_TOKEN") and e("TELEGRAM_CHAT_ID"):
        try:
            requests.post(f"https://api.telegram.org/bot{e('TELEGRAM_BOT_TOKEN')}/sendMessage",
                          json={"chat_id": e("TELEGRAM_CHAT_ID"), "text": f"{title}\n\n{body}" + (f"\n\n{url}" if url else "")},
                          timeout=20).raise_for_status()
            sent.append("telegram")
        except Exception as ex:
            print("  ! telegram failed:", ex)
    if e("WA_TOKEN") and e("WA_PHONE_ID") and e("WA_TO"):
        try:
            # Meta only allows free-form text inside 24h of your last message to the number.
            # Outside that window you must use an approved template (set WA_TEMPLATE, one body variable).
            api = f"https://graph.facebook.com/v20.0/{e('WA_PHONE_ID')}/messages"
            if e("WA_TEMPLATE"):
                payload = {"messaging_product": "whatsapp", "to": e("WA_TO"), "type": "template",
                           "template": {"name": e("WA_TEMPLATE"), "language": {"code": "en"},
                                        "components": [{"type": "body", "parameters": [
                                            {"type": "text", "text": body.replace("\n", " | ")[:900]}]}]}}
            else:
                payload = {"messaging_product": "whatsapp", "to": e("WA_TO"), "type": "text",
                           "text": {"body": f"{title}\n\n{body}"[:3900]}}
            requests.post(api, json=payload, headers={"Authorization": f"Bearer {e('WA_TOKEN')}"}, timeout=25).raise_for_status()
            sent.append("whatsapp")
        except Exception as ex:
            print("  ! whatsapp failed:", ex)
    if e("SMTP_USER") and e("SMTP_PASS"):
        try:
            m = EmailMessage()
            m["Subject"], m["From"], m["To"] = title, e("SMTP_USER"), e("MAIL_TO") or e("SMTP_USER")
            m.set_content(body + (f"\n\n{url}" if url else ""))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(e("SMTP_USER"), e("SMTP_PASS"))
                s.send_message(m)
            sent.append("email")
        except Exception as ex:
            print("  ! email failed:", ex)
    return sent
