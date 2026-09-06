#!/usr/bin/env python3
"""
One Gemini request, with the free tier's failure modes handled.

Both score.py and draft.py call the same endpoint under the same limits,
so the retry policy lives here rather than in each of them.

The free tier allows roughly 10-15 requests per minute plus a daily cap
that varies by model, and the limits apply per project, not per key:

  - a per-minute 429 backs off and retries
  - a daily-cap 429 stops the run, because backoff cannot refill a quota
    that resets at midnight Pacific
  - 500/503 back off too: the shared capacity sheds load often enough to
    stall a run otherwise
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 90
MAX_RETRIES = 4

# Pinned rather than the "gemini-flash-latest" alias, which returns 503 under
# load often enough to stall a run. Retired models 404 with a clear message,
# so when this one ages out, set GEMINI_MODEL or bump this line.
DEFAULT_MODEL = "gemini-3.5-flash"


def config() -> tuple[str, str]:
    """Return (api_key, model), exiting with instructions if the key is absent."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set. Add it to .env (locally) or the "
                 "repo secrets (CI). Free keys: aistudio.google.com/apikey")
    return api_key, os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _quota_violations(resp: requests.Response) -> list[str]:
    """
    Return the quota ids named in a 429 body, or [] when it carries none.

    Gemini says which window it hit in error.details[].violations[].quotaId
    ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier" vs the PerDay
    one). The prose message names neither — it just links the rate-limit
    docs — so matching substrings against the whole body can read a
    per-minute 429, which backoff fixes, as a daily cap, which ends the run.
    """
    try:
        details = resp.json()["error"]["details"]
    except (ValueError, KeyError, TypeError):
        return []
    ids: list[str] = []
    for detail in details:
        if str(detail.get("@type", "")).endswith("QuotaFailure"):
            ids.extend(v.get("quotaId", "") for v in detail.get("violations", []))
    return [i for i in ids if i]


def generate(prompt: str, api_key: str, model: str,
             temperature: float = 0.2) -> str:
    """
    Send one prompt and return the model's text, asking for JSON output.

    Raises SystemExit on anything retrying cannot fix, with a message that
    says what to do next.
    """
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    delay = 5
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL.format(model=model), headers=headers,
                                 json=body, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES:
                raise SystemExit(f"Gemini timed out after {TIMEOUT}s on "
                                 f"{MAX_RETRIES} attempts. Re-run later; any "
                                 "work already written is saved.")
            time.sleep(delay)
            delay *= 2
            continue
        except requests.exceptions.RequestException as exc:
            raise SystemExit(f"Could not reach Gemini: {type(exc).__name__}: {exc}")

        if resp.status_code == 429:
            quota_ids = _quota_violations(resp)
            # Log the evidence before acting on it. A daily cap ends the run,
            # and in CI a misclassified per-minute 429 leaves an identical red
            # job with nothing to tell the two apart afterwards.
            print("  Gemini 429 · " + (", ".join(quota_ids)
                                       or resp.text[:200].replace("\n", " ")))
            if quota_ids:
                hit_daily = any("perday" in q.lower() for q in quota_ids)
            else:
                # No structured violation: the prose is all there is to go on.
                detail = resp.text.lower()
                hit_daily = ("perday" in detail or "per day" in detail
                             or "daily" in detail)
            if hit_daily:
                raise SystemExit(
                    "Gemini daily quota is spent. Anything already written is "
                    "saved. The quota resets at midnight Pacific — re-run then, "
                    "or set GEMINI_MODEL to a different free-tier Flash.")
            if attempt == MAX_RETRIES:
                raise SystemExit(f"Gemini kept returning 429 after {MAX_RETRIES} "
                                 "attempts. Slow the caller down and re-run.")
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code >= 500:
            if attempt == MAX_RETRIES:
                raise SystemExit(
                    f"Gemini returned HTTP {resp.status_code} on every one of "
                    f"{MAX_RETRIES} attempts — the model is overloaded. Re-run "
                    "later, or set GEMINI_MODEL to another Flash model.")
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 400 and "API_KEY" in resp.text.upper():
            raise SystemExit("Gemini rejected the API key. Check GEMINI_API_KEY "
                             "in .env (or the repo secret in CI).")
        if resp.status_code == 404:
            raise SystemExit(f"No such model: {model}. Retired models 404 — set "
                             "GEMINI_MODEL to a model your key can use.")
        if resp.status_code >= 400:
            raise SystemExit(f"Gemini returned HTTP {resp.status_code}: "
                             f"{resp.text[:300]}")

        payload = resp.json()
        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            reason = payload.get("promptFeedback", {}).get("blockReason", "")
            print(f"  warning: no usable candidate in response {reason}".rstrip())
            return ""

    return ""
