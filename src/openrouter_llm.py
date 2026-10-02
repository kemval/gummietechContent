#!/usr/bin/env python3
"""
One OpenRouter request, mirroring groq_llm.py's interface so llm.py can fail
over to it. Always the last link in llm.FALLBACK_ORDER.

config() -> (api_key, model)
generate(prompt, api_key, model, temperature=0.2) -> str  (raw JSON text)

Why it exists: on 2026-10-02 Gemini returned 503s all afternoon while Groq's
daily cap was spent, and there was nothing left to draft with. Two
candidates for a third free provider fell through that day: Cerebras needs
a card for a one-time credit, and GitHub Models had been retired on
2026-07-30 (docs/decisions/llm-providers.md).

Terms, from OpenRouter's docs on 2026-10-02 — stated so they can be designed
around, not discovered:

  - Only `:free` model ids cost nothing: 20 requests a minute and 50 a day
    across all of them, no card. (1,000 a day needs a one-time $10 purchase,
    which CLAUDE.md's $0 rule rules out.) config() refuses any other id, so
    a typo in OPENROUTER_MODEL cannot reach a paid model.
  - The free list rotates — OpenRouter says less popular models leave it —
    so the model is OPENROUTER_MODEL, not a constant buried in code.
  - Most free endpoints are served by providers that may log prompts. They
    are only routed to once the account's privacy settings allow it;
    otherwise every call is a 503 "no available model provider that meets
    your routing requirements". That 503 is configuration, not overload, so
    it stops the run with that hint instead of raising Overloaded.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from llm_errors import Overloaded

REPO_ROOT = Path(__file__).resolve().parent.parent

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 90
MAX_RETRIES = 4

# Free and JSON-mode capable on 2026-10-02 (response_format listed in the
# public /api/v1/models). nvidia/nemotron-3-super-120b-a12b:free was the
# other candidate.
DEFAULT_MODEL = "google/gemma-4-31b-it:free"
FREE_SUFFIX = ":free"


def config() -> tuple[str, str]:
    """Return (api_key, model), exiting with instructions if either is unusable."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY is not set. Add it to .env (locally) or "
                 "the repo secrets (CI). Keys: openrouter.ai/settings/keys")
    model = os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
    if not model.endswith(FREE_SUFFIX):
        sys.exit(f"OPENROUTER_MODEL={model!r} is not a free model. Only ids "
                 f"ending in {FREE_SUFFIX!r} cost nothing — CLAUDE.md's $0 "
                 "rule. Pick one from openrouter.ai/models?max_price=0")
    return api_key, model


def error_message(resp: requests.Response) -> str:
    """OpenRouter's {"error": {"message": ...}}, or the raw body."""
    try:
        return str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return resp.text[:300]


def generate(prompt: str, api_key: str, model: str,
             temperature: float = 0.2) -> str:
    """
    Send one prompt and return the model's text, asking for JSON output.

    Raises Overloaded when 502 outlasts the retries, and SystemExit on
    anything else retrying cannot fix, with a message that says what to do
    next — the same contract as groq_llm.generate().
    """
    if "json" not in prompt.lower():
        prompt = prompt + "\n\nRespond with JSON only."

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json",
               # Optional attribution headers, per OpenRouter's quickstart.
               "HTTP-Referer": "https://kemval.github.io/gummietechContent/",
               "X-OpenRouter-Title": "gummietech"}

    delay = 5
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=body,
                                 timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES:
                raise SystemExit(f"OpenRouter timed out after {TIMEOUT}s on "
                                 f"{MAX_RETRIES} attempts. Re-run later; any "
                                 "work already written is saved.")
            time.sleep(delay)
            delay *= 2
            continue
        except requests.exceptions.RequestException as exc:
            raise SystemExit("Could not reach OpenRouter: "
                             f"{type(exc).__name__}: {exc}")

        if resp.status_code == 429:
            message = error_message(resp)
            print(f"  OpenRouter 429 · {message[:200]}")
            # The free tier's daily cap names itself ("free-models-per-day");
            # unverified against a live response, like groq_llm.py's parse.
            if "per-day" in message.lower() or "per day" in message.lower():
                raise SystemExit("OpenRouter's free daily cap (50 requests) "
                                 "is spent. Anything already written is saved.")
            if attempt == MAX_RETRIES:
                raise SystemExit(f"OpenRouter kept returning 429 after "
                                 f"{MAX_RETRIES} attempts. Re-run later.")
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code in (502, 408) or resp.status_code > 503:
            if attempt == MAX_RETRIES:
                raise Overloaded(
                    f"OpenRouter returned HTTP {resp.status_code} on every one "
                    f"of {MAX_RETRIES} attempts — {model} is down. Re-run "
                    "later, or set OPENROUTER_MODEL to another free model.")
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 503:
            raise SystemExit(
                f"OpenRouter has no provider for {model} that your account "
                f"allows: {error_message(resp)[:200]}. Free models are mostly "
                "served by providers that may log prompts — allow them in "
                "openrouter.ai/settings/privacy, or pick another free model.")
        if resp.status_code == 401:
            raise SystemExit("OpenRouter rejected the API key. Check "
                             "OPENROUTER_API_KEY in .env (or the repo secret).")
        if resp.status_code == 402:
            raise SystemExit("OpenRouter says the account has a negative "
                             "balance, which blocks even free models. Check "
                             "openrouter.ai/settings/credits.")
        if resp.status_code == 404:
            raise SystemExit(f"OpenRouter has no model {model}. Free models "
                             "rotate: set OPENROUTER_MODEL to one listed at "
                             "openrouter.ai/models?max_price=0")
        if resp.status_code >= 400:
            raise SystemExit(f"OpenRouter returned HTTP {resp.status_code}: "
                             f"{error_message(resp)[:300]}")

        try:
            payload = resp.json()
        except ValueError:
            raise SystemExit(f"OpenRouter answered HTTP {resp.status_code} "
                             f"with no JSON: {resp.text[:80]!r}")
        # An error can arrive inside a 200 when the upstream provider fails.
        if "error" in payload and "choices" not in payload:
            raise SystemExit(f"OpenRouter's provider failed: "
                             f"{str(payload['error'])[:300]}")
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            print(f"  warning: no usable choice in response: {payload}")
            return ""

    return ""
