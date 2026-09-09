#!/usr/bin/env python3
"""
One Groq request, mirroring gemini.py's interface so draft.py/score.py can
swap providers by changing a single import line.

config() -> (api_key, model)
generate(prompt, api_key, model, temperature=0.2) -> str  (raw JSON text)

Groq's free tier is rate-limited per-minute and per-day, similar in shape to
Gemini's, but the quota-id classification Gemini uses does not apply here —
Groq's 429 body is plain JSON with a "message" field, not structured
QuotaFailure violations. So daily-vs-per-minute is detected by parsing the
message text and the response headers Groq sends back
(retry-after, x-ratelimit-*), which is the closest analogue available.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

API_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT = 90
MAX_RETRIES = 4

# llama-3.3-70b-versatile is Groq's general-purpose free-tier model as of
# this writing. Swap via GROQ_MODEL if it's retired or renamed.
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def config() -> tuple[str, str]:
    """Return (api_key, model), exiting with instructions if the key is absent."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("GROQ_API_KEY is not set. Add it to .env (locally) or the "
                 "repo secrets (CI). Free keys: console.groq.com/keys")
    return api_key, os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


def generate(prompt: str, api_key: str, model: str,
             temperature: float = 0.2) -> str:
    """
    Send one prompt and return the model's text, asking for JSON output.

    Raises SystemExit on anything retrying cannot fix, with a message that
    says what to do next. Mirrors gemini.generate()'s contract: same
    signature, same return type, same fail-fast-on-daily-cap behavior.
    """
    # Groq's JSON mode requires the word "json" to appear in the prompt
    # somewhere, or the API rejects the request outright (400) rather than
    # silently ignoring response_format.
    if "json" not in prompt.lower():
        prompt = prompt + "\n\nRespond with JSON only."

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}

    delay = 5
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=body,
                                 timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES:
                raise SystemExit(f"Groq timed out after {TIMEOUT}s on "
                                 f"{MAX_RETRIES} attempts. Re-run later; any "
                                 "work already written is saved.")
            time.sleep(delay)
            delay *= 2
            continue
        except requests.exceptions.RequestException as exc:
            raise SystemExit(f"Could not reach Groq: {type(exc).__name__}: {exc}")

        if resp.status_code == 429:
            # Groq exposes the window in headers when present; fall back to
            # the message text. Unverified against a live daily-cap response,
            # so this classification is a best guess, not a confirmed parse
            # the way the Gemini quotaId check is - if it misclassifies a
            # per-minute 429 as daily, adjust the "daily" keyword check below
            # against whatever text your account actually returns.
            detail = resp.text.lower()
            print(f"  Groq 429 · {resp.text[:200]}")
            hit_daily = "day" in detail and "minute" not in detail
            if hit_daily:
                raise SystemExit(
                    "Groq daily quota looks spent (best-effort parse of the "
                    "429 body — verify against the actual message above). "
                    "Anything already written is saved.")
            if attempt == MAX_RETRIES:
                raise SystemExit(f"Groq kept returning 429 after {MAX_RETRIES} "
                                 "attempts. Slow the caller down and re-run.")
            retry_after = resp.headers.get("retry-after")
            time.sleep(float(retry_after) if retry_after else delay)
            delay *= 2
            continue

        if resp.status_code >= 500:
            if attempt == MAX_RETRIES:
                raise SystemExit(
                    f"Groq returned HTTP {resp.status_code} on every one of "
                    f"{MAX_RETRIES} attempts — the model is overloaded. Re-run "
                    "later, or set GROQ_MODEL to another model.")
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 401:
            raise SystemExit("Groq rejected the API key. Check GROQ_API_KEY "
                             "in .env (or the repo secret in CI).")
        if resp.status_code == 404:
            raise SystemExit(f"No such model: {model}. Set GROQ_MODEL to a "
                             "model your key can use (see console.groq.com).")
        if resp.status_code >= 400:
            raise SystemExit(f"Groq returned HTTP {resp.status_code}: "
                             f"{resp.text[:300]}")

        payload = resp.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            print(f"  warning: no usable choice in response: {payload}")
            return ""

    return ""