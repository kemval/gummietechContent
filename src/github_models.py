#!/usr/bin/env python3
"""
One GitHub Models request, mirroring groq_llm.py's interface so llm.py can
fail over to it.

config() -> (api_key, model)
generate(prompt, api_key, model, temperature=0.2) -> str  (raw JSON text)

The third free provider, added on 2026-10-02: Gemini shed load all that
afternoon while Groq's daily cap was spent, and nothing was left to draft
with. GitHub Models is free with the account the repo already lives on — no
card, no new secret. In Actions the workflow's own token reaches it once the
job has `permissions: models: read`; the workflows pass `github.token` in as
GITHUB_MODELS_TOKEN. Locally, a personal token with the models:read
permission works the same way.

Cerebras was considered first and rejected for CLAUDE.md's $0 rule: its
"free" tier needs a card and is a one-time $5 credit that pauses access
when it runs out — a backup that stops working in a month.

Free-tier limits, from GitHub's docs on 2026-10-02 (stated here so they can
be designed around, not discovered): roughly 10 requests a minute and a
daily cap of ~50 requests for "high" models or ~150 for "low" ones, with
8,000 tokens in and 4,000 out per request. That is plenty as a fallback and
not enough as a primary — which is why it is only ever the third choice.
The daily-vs-per-minute 429 split below is unverified against a live
response, like groq_llm.py's was.
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

API_URL = "https://models.github.ai/inference/chat/completions"
TIMEOUT = 90
MAX_RETRIES = 4
# A wait longer than this is a daily cap, not a per-minute one: sleeping
# through it would spend the job's timeout and land in the same place.
MAX_WAIT = 120

# A "low"-tier model, for the larger daily allowance. Unverified against
# the live catalogue when written — set GITHUB_MODELS_MODEL if it 404s
# (the catalogue is at https://github.com/marketplace/models).
DEFAULT_MODEL = "openai/gpt-4.1-mini"


def config() -> tuple[str, str]:
    """Return (token, model), exiting with instructions if the token is absent."""
    load_dotenv(REPO_ROOT / ".env")
    token = os.environ.get("GITHUB_MODELS_TOKEN")
    if not token:
        sys.exit("GITHUB_MODELS_TOKEN is not set. In CI, pass "
                 "${{ github.token }} and give the job `permissions: models: "
                 "read`; locally, use a token with the models:read permission.")
    return token, os.environ.get("GITHUB_MODELS_MODEL") or DEFAULT_MODEL


def generate(prompt: str, api_key: str, model: str,
             temperature: float = 0.2) -> str:
    """
    Send one prompt and return the model's text, asking for JSON output.

    Raises Overloaded when 5xx outlasts the retries, and SystemExit on
    anything else retrying cannot fix, with a message that says what to do
    next — the same contract as gemini.generate() and groq_llm.generate().
    """
    # OpenAI-style JSON mode rejects a prompt that never says "json".
    if "json" not in prompt.lower():
        prompt = prompt + "\n\nRespond with JSON only."

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}",
               "Accept": "application/vnd.github+json",
               "Content-Type": "application/json"}

    delay = 5
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=body,
                                 timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES:
                raise SystemExit(f"GitHub Models timed out after {TIMEOUT}s on "
                                 f"{MAX_RETRIES} attempts. Re-run later; any "
                                 "work already written is saved.")
            time.sleep(delay)
            delay *= 2
            continue
        except requests.exceptions.RequestException as exc:
            raise SystemExit("Could not reach GitHub Models: "
                             f"{type(exc).__name__}: {exc}")

        if resp.status_code == 429:
            print(f"  GitHub Models 429 · {resp.text[:200]}")
            try:
                wait = float(resp.headers.get("retry-after", delay))
            except ValueError:
                wait = delay
            if wait > MAX_WAIT:
                raise SystemExit(
                    f"GitHub Models asks for a {wait:.0f}s wait — its daily "
                    "cap looks spent (best-effort reading of retry-after). "
                    "Anything already written is saved.")
            if attempt == MAX_RETRIES:
                raise SystemExit(f"GitHub Models kept returning 429 after "
                                 f"{MAX_RETRIES} attempts. Re-run later.")
            time.sleep(wait)
            delay *= 2
            continue

        if resp.status_code >= 500:
            if attempt == MAX_RETRIES:
                raise Overloaded(
                    f"GitHub Models returned HTTP {resp.status_code} on every "
                    f"one of {MAX_RETRIES} attempts. Re-run later.")
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code in (401, 403):
            raise SystemExit("GitHub Models refused the token. In CI the job "
                             "needs `permissions: models: read`; locally the "
                             "token needs the models:read permission.")
        if resp.status_code == 404:
            raise SystemExit(f"No such model on GitHub Models: {model}. Set "
                             "GITHUB_MODELS_MODEL to one in the catalogue.")
        if resp.status_code == 413:
            raise SystemExit("The prompt is over GitHub Models' 8,000-token "
                             "request limit. Shorten it, or re-run when the "
                             "other providers are back.")
        if resp.status_code >= 400:
            raise SystemExit(f"GitHub Models returned HTTP {resp.status_code}: "
                             f"{resp.text[:300]}")

        # 2026-10-02, the first live call: HTTP 200 with a plain-text "OK"
        # body, from Actions and from a laptop alike, and json() raised a
        # traceback. Whatever the endpoint has become, that is not an answer.
        try:
            payload = resp.json()
        except ValueError:
            raise SystemExit(
                f"GitHub Models answered HTTP {resp.status_code} with no JSON "
                f"({resp.headers.get('content-type', 'no content type')}: "
                f"{resp.text[:80]!r}). {API_URL} may have moved — check "
                "GitHub's Models docs before relying on this fallback.")
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            print(f"  warning: no usable choice in response: {payload}")
            return ""

    return ""
