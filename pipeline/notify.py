"""Daily push. Configure any of these via environment variables / GitHub secrets; unset channels are skipped.

App push (own PWA, no app):  VAPID_PRIVATE_KEY + VAPID_SUBJECT + PUSH_SUBS (JSON sub, or list of them)
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


def _web_push(title, body, url, sent):
    """Send to the installed PWA directly via the Web Push protocol (VAPID). No third-party app."""
    import json
    e = os.environ.get
    priv, subs_raw = e("VAPID_PRIVATE_KEY"), e("PUSH_SUBS")
    # pywebpush needs 'sub' as a mailto: link; default avoids an extra secret and keeps no personal email in the repo.
    subj = e("VAPID_SUBJECT") or "mailto:aldrindsouza3-dotcom@users.noreply.github.com"
    if not (priv and subs_raw):
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("  ! pywebpush not installed"); return
    # Accept the private key as raw base64url (what the browser/py-vapid generate); pywebpush wants a PEM FILE path.
    import os as _os, tempfile
    key_path = None
    try:
        if "BEGIN" in priv:
            pem = priv
        else:
            import base64
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            d = base64.urlsafe_b64decode(priv.strip() + "=" * (-len(priv.strip()) % 4))
            pem = ec.derive_private_key(int.from_bytes(d, "big"), ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        fp = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        fp.write(pem); fp.close(); key_path = fp.name
    except Exception as ex:
        print("  ! could not parse VAPID_PRIVATE_KEY:", str(ex)[:120]); return
    subs_raw = subs_raw.strip()
    try:  # accept one subscription object, or a JSON array of them
        parsed = json.loads(subs_raw)
        subs = parsed if isinstance(parsed, list) else [parsed]
    except Exception as ex:
        print("  ! PUSH_SUBS not valid JSON:", ex); return
    payload = json.dumps({"title": title, "body": body, "url": url or "./"})
    ok = 0
    for s in subs:
        try:
            webpush(subscription_info=s, data=payload, vapid_private_key=key_path, vapid_claims={"sub": subj})
            ok += 1
        except WebPushException as ex:
            body = ""
            try:
                body = ex.response.text[:300] if ex.response is not None else ""
            except Exception:
                pass
            print("  ! web push failed:", str(ex)[:100], "| body:", body)
        except Exception as ex:
            print("  ! web push error:", str(ex)[:120])
    try:
        if key_path:
            _os.unlink(key_path)
    except Exception:
        pass
    if ok:
        sent.append(f"app-push x{ok}")


def send_all(title: str, body: str, url: str | None = None) -> list[str]:
    sent = []
    e = os.environ.get
    _web_push(title, body, url, sent)
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
