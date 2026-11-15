"""Optional Claude-powered layer (personal use). Runs only if ANTHROPIC_API_KEY is set.

It writes a plain-language daily market brief and a one-line 'why selected' for each shortlisted stock,
grounded strictly in the numbers we pass in (the model must not invent figures). Degrades to None if no
key or any error, so the pipeline never depends on it.
"""
from __future__ import annotations

import json
import os

MODEL = os.environ.get("AI_MODEL", "claude-haiku-5-5")  # cheap + fast for a daily brief
DISCLAIMER = "Research aid, not advice. End-of-day data."


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except Exception as e:
        print("  ! anthropic SDK not available:", str(e)[:100])
        return None


def market_brief(context: dict) -> dict | None:
    """context: regime, breadth, index snapshot, trading_top5, investing_top5 (names+scores+verdicts+key numbers).
    Returns {brief, trading_reasons:{sym:line}, investing_reasons:{sym:line}} or None."""
    c = _client()
    if c is None:
        return None
    sys_prompt = (
        "You are a careful Indian-markets analyst writing for one retail investor inside their personal "
        "end-of-day dashboard. You are given COMPUTED facts as JSON. Rules: use ONLY those numbers, never "
        "invent prices/percentages; be concise and plain; explain the 'why' in everyday language; never promise "
        "returns; always sound measured. Output STRICT JSON with keys: brief (3-4 sentence market overview), "
        "trading_reasons (object mapping each trading symbol to ONE sentence on why it was shortlisted for a swing "
        "trade, citing its given numbers), investing_reasons (same for investing symbols, emphasising quality/"
        "valuation/long-term trend). No markdown, JSON only."
    )
    try:
        msg = c.messages.create(
            model=MODEL, max_tokens=1100, system=sys_prompt,
            messages=[{"role": "user", "content": json.dumps(context)[:9000]}],
        )
        txt = msg.content[0].text.strip()
        if txt.startswith("```"):
            txt = txt.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(txt)
        data["model"] = MODEL
        return data
    except Exception as e:
        print("  ! AI brief failed:", str(e)[:140])
        return None
