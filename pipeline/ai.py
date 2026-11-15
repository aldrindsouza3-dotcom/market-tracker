"""Optional AI layer (personal use) — daily market brief + 'why selected' per stock.

Free, no-card providers are supported via environment variables; the first key present wins:
  OPENROUTER_API_KEY  (free, open-source Llama)   -> set AI_MODEL to override (default llama-3.3-70b:free)
  GROQ_API_KEY        (free, fast Llama)
  GEMINI_API_KEY      (free Google Gemini)
  ANTHROPIC_API_KEY   (paid Claude)
Grounded strictly in the numbers passed in (must not invent figures). Returns None on no key / error,
so the pipeline never depends on it.
"""
from __future__ import annotations

import json
import os

import requests

SYS = (
    "You are a careful Indian-markets analyst writing for one retail investor inside their personal "
    "end-of-day dashboard. You are given COMPUTED facts as JSON. Rules: use ONLY those numbers, never "
    "invent prices/percentages; be concise and plain; explain the 'why' in everyday language; never promise "
    "returns. Output STRICT JSON with keys: brief (3-4 sentence market overview), trading_reasons (object "
    "mapping each trading symbol to ONE sentence why it was shortlisted for a swing trade, citing its numbers), "
    "investing_reasons (same for investing symbols, emphasising quality/valuation/long-term trend). JSON only, no markdown."
)


def _provider():
    e = os.environ.get
    if e("OPENROUTER_API_KEY"):
        return ("openai", "https://openrouter.ai/api/v1/chat/completions", e("OPENROUTER_API_KEY"),
                e("AI_MODEL", "meta-llama/llama-3.3-70b-instruct:free"))
    if e("GROQ_API_KEY"):
        return ("openai", "https://api.groq.com/openai/v1/chat/completions", e("GROQ_API_KEY"),
                e("AI_MODEL", "llama-3.3-70b-versatile"))
    if e("GEMINI_API_KEY"):
        return ("gemini", "https://generativelanguage.googleapis.com/v1beta/models", e("GEMINI_API_KEY"),
                e("AI_MODEL", "gemini-flash-latest"))
    if e("ANTHROPIC_API_KEY"):
        return ("anthropic", "https://api.anthropic.com/v1/messages", e("ANTHROPIC_API_KEY"),
                e("AI_MODEL", "claude-haiku-5-5"))
    return None


def _ask(prompt: str) -> str | None:
    p = _provider()
    if not p:
        return None
    kind, url, key, model = p
    try:
        if kind == "openai":
            r = requests.post(url, timeout=60, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"model": model, "max_tokens": 1100,
                                    "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        if kind == "gemini":
            r = requests.post(f"{url}/{model}:generateContent?key={key}", timeout=60,
                              json={"system_instruction": {"parts": [{"text": SYS}]},
                                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                    "generationConfig": {"maxOutputTokens": 1100}})
            r.raise_for_status()
            return "".join(p["text"] for p in r.json()["candidates"][0]["content"]["parts"])
        if kind == "anthropic":
            import anthropic
            m = anthropic.Anthropic(api_key=key).messages.create(
                model=model, max_tokens=1100, system=SYS, messages=[{"role": "user", "content": prompt}])
            return m.content[0].text
    except Exception as e:
        print("  ! AI call failed:", str(e)[:140])
    return None


def market_brief(context: dict) -> dict | None:
    raw = _ask(json.dumps(context)[:9000])
    if not raw:
        return None
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        data = json.loads(txt)
    except Exception:
        # some models wrap or add prose; grab the first {...} block
        import re
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            print("  ! AI brief not JSON")
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    p = _provider()
    data["model"] = p[3] if p else None
    return data
