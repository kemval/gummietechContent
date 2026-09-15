#!/usr/bin/env python3
"""
Selects the pipeline's LLM backend once, so score.py, draft.py and
translate.py don't each carry a conditional import.

All three callers use the same two-function interface:

    config() -> (api_key, model)
    generate(prompt, api_key, model, temperature=0.2) -> str  (raw JSON text)

gemini.py and groq_llm.py both implement it. This module forwards to
whichever one LLM_PROVIDER names, defaulting to Gemini.

Why a module and not an import line in each caller: LLM_PROVIDER lives in
.env, not the shell, so the choice has to be read after load_dotenv().
Doing that in three callers invites them to drift; doing it here keeps the
choice — and the failover below — in one spot.

Failover: Gemini's free tier sheds load with 503s often enough to kill a
whole run. Four of the eight scheduled ingests on 2026-09-14/15 died that
way, each on its first batch, leaving the sheet full of items still marked
'new'. So when the chosen provider returns 5xx on every retry, this module
switches to the other free provider and says so.

Two things that failover deliberately is not:

  - **Only 5xx exhaustion triggers it.** A rejected key or a retired model
    is a configuration error that wants fixing, not routing around. A spent
    daily cap could in principle fail over, but sending a whole day's
    scoring to the other provider would hide the cap and spend the budget
    draft.py needs later. All of those still stop the run where they happen.
  - **The switch is sticky for the process.** An overload window outlives
    one request, so re-trying the dead provider on every batch would spend
    the job's 15-minute timeout on backoff and reach the same place.

CLAUDE.md budget constraint: both providers must stay on their free tier.
Never point this at a paid API — the Groq/Gemini free tiers are the only
sanctioned scoring backends.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

from dotenv import load_dotenv

# Neither backend reads the environment at import time — config() does that —
# so both can be imported here and the failover picks between them.
import gemini
import groq_llm
from llm_errors import Overloaded

REPO_ROOT = Path(__file__).resolve().parent.parent

# Read .env before deciding which provider to use.
load_dotenv(REPO_ROOT / ".env")

BACKENDS: dict[str, ModuleType] = {"gemini": gemini, "groq": groq_llm}

PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini"
if PROVIDER not in BACKENDS:
    sys.exit(f"LLM_PROVIDER={PROVIDER!r} is not a known provider. Set it to "
             "'gemini' or 'groq' in .env, or leave it unset for Gemini.")

FALLBACK = "groq" if PROVIDER == "gemini" else "gemini"

_backend = BACKENDS[PROVIDER]

# (backend, api_key, model) once the primary has failed over; None until then.
_failover: tuple[ModuleType, str, str] | None = None

# Re-exported so callers can write llm.config() — the chosen provider's key
# and model, which is what they print and pass back into generate().
config = _backend.config


def _start_failover(exc: Overloaded) -> tuple[ModuleType, str, str]:
    """
    Configure the other provider, or stop the run the way the caller expected.

    The fallback's config() exits when its key is missing, which is exactly
    the "there is nothing to switch to" case — so catch that and re-raise the
    overload as the SystemExit it would have been before failover existed.
    Its message already says what to do next.
    """
    fallback = BACKENDS[FALLBACK]
    try:
        api_key, model = fallback.config()
    except SystemExit:
        raise SystemExit(
            f"{exc}\nNothing to fall back to: {FALLBACK.upper()}_API_KEY is "
            "not set. Add it to .env (locally) or the repo secrets (CI) and "
            f"{PROVIDER} overloading will switch to {FALLBACK} instead of "
            "ending the run.")
    print(f"  {PROVIDER} is overloaded — switching to {FALLBACK} ({model}) "
          "for the rest of this run.")
    return fallback, api_key, model


def generate(prompt: str, api_key: str, model: str,
             temperature: float = 0.2) -> str:
    """
    Send one prompt through the chosen provider, failing over on overload.

    api_key and model are the ones config() returned, and are ignored once a
    failover is in effect — the fallback's own credentials replace them.
    Raises SystemExit on anything neither provider can be retried past, so a
    caller that just wants text never has to know two backends exist.
    """
    global _failover

    if _failover is None:
        try:
            return _backend.generate(prompt, api_key, model, temperature)
        except Overloaded as exc:
            _failover = _start_failover(exc)

    backend, fb_key, fb_model = _failover
    try:
        return backend.generate(prompt, fb_key, fb_model, temperature)
    except Overloaded as exc:
        raise SystemExit(
            f"{exc}\nBoth free providers are shedding load — {PROVIDER} first, "
            f"then {FALLBACK}. Re-run later; anything already written is saved.")
