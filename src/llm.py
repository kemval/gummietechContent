#!/usr/bin/env python3
"""
Selects the pipeline's LLM backend once, so score.py, draft.py and
translate.py don't each carry a conditional import.

All three callers use the same two-function interface:

    config() -> (api_key, model)
    generate(prompt, api_key, model, temperature=0.2) -> str  (raw JSON text)

gemini.py, groq_llm.py and openrouter_llm.py implement it. This module
forwards to whichever one LLM_PROVIDER names, defaulting to Gemini.

Why a module and not an import line in each caller: LLM_PROVIDER lives in
.env, not the shell, so the choice has to be read after load_dotenv().
Doing that in three callers invites them to drift; doing it here keeps the
choice — and the failover below — in one spot.

Failover: Gemini's free tier sheds load with 503s often enough to kill a
whole run. Four of the eight scheduled ingests on 2026-09-14/15 died that
way, each on its first batch, leaving the sheet full of items still marked
'new'. So when the chosen provider returns 5xx on every retry, this module
switches to the next free provider in FALLBACK_ORDER and says so. A
fallback with no key configured is skipped, not fatal. OpenRouter's free
models (openrouter_llm.py) are the third link, always last: 50 requests a
day is a backstop, not a supply (docs/decisions/llm-providers.md).

Two things that failover deliberately is not:

  - **Only 5xx exhaustion triggers it.** A rejected key or a retired model
    is a configuration error that wants fixing, not routing around. A spent
    daily cap could in principle fail over, but sending a whole day's
    scoring to the other provider would hide the cap and spend the budget
    draft.py needs later. All of those still stop the run where they happen.
  - **The switch is sticky for the process.** An overload window outlives
    one request, so re-trying the dead provider on every batch would spend
    the job's 15-minute timeout on backoff and reach the same place.

CLAUDE.md budget constraint: every provider must stay on its free tier.
Never point this at a paid API — the Gemini, Groq and OpenRouter `:free`
tiers are the only sanctioned backends.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

from dotenv import load_dotenv

# None of the backends reads the environment at import time — config() does
# that — so all of them can be imported here and the failover picks.
import gemini
import groq_llm
import openrouter_llm
from llm_errors import Overloaded

REPO_ROOT = Path(__file__).resolve().parent.parent

# Read .env before deciding which provider to use.
load_dotenv(REPO_ROOT / ".env")

BACKENDS: dict[str, ModuleType] = {"gemini": gemini, "groq": groq_llm,
                                   "openrouter": openrouter_llm}
# The order fallbacks are tried in, after whichever one LLM_PROVIDER names.
# OpenRouter is last: its free cap (50 requests a day) cannot carry a day.
FALLBACK_ORDER = ("gemini", "groq", "openrouter")

PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini"
if PROVIDER not in BACKENDS:
    sys.exit(f"LLM_PROVIDER={PROVIDER!r} is not a known provider. Set it to "
             f"one of {', '.join(BACKENDS)} in .env, or leave it unset for "
             "Gemini.")

FALLBACKS = [name for name in FALLBACK_ORDER if name != PROVIDER]

_backend = BACKENDS[PROVIDER]

# (name, backend, api_key, model) once the primary has failed over, and the
# fallbacks not yet tried. Module state because the switch is sticky.
_failover: tuple[str, ModuleType, str, str] | None = None
_untried: list[str] = list(FALLBACKS)

# Re-exported so callers can write llm.config() — the chosen provider's key
# and model, which is what they print and pass back into generate().
config = _backend.config


def _next_provider(exc: Overloaded, failed: list[str]
                   ) -> tuple[str, ModuleType, str, str]:
    """
    Configure the next fallback that has a key, or stop the run.

    A fallback's config() exits when its key is missing; that one is skipped
    and the next tried. When none is left, the overload becomes the
    SystemExit it would have been with no failover, naming what was tried
    and which keys were missing — that is what to do next.
    """
    missing = []
    while _untried:
        name = _untried.pop(0)
        try:
            api_key, model = BACKENDS[name].config()
        except SystemExit:
            missing.append(name)
            continue
        print(f"  {failed[-1]} is overloaded — switching to {name} ({model}) "
              "for the rest of this run.")
        return name, BACKENDS[name], api_key, model
    note = (f" No key for {', '.join(missing)}: add it to .env (locally) or "
            "the workflow (CI) and an overload will fall through to it."
            if missing else "")
    raise SystemExit(f"{exc}\nEvery configured provider is shedding load "
                     f"({' then '.join(failed)}). Re-run later; anything "
                     f"already written is saved.{note}")


def generate(prompt: str, api_key: str, model: str,
             temperature: float = 0.2) -> str:
    """
    Send one prompt through the chosen provider, failing over on overload.

    api_key and model are the ones config() returned, and are ignored once a
    failover is in effect — the fallback's own credentials replace them.
    Raises SystemExit on anything no provider can be retried past, so a
    caller that just wants text never has to know there are several.
    """
    global _failover

    failed = [PROVIDER]
    if _failover is None:
        try:
            return _backend.generate(prompt, api_key, model, temperature)
        except Overloaded as exc:
            _failover = _next_provider(exc, failed)

    while True:
        name, backend, fb_key, fb_model = _failover
        try:
            return backend.generate(prompt, fb_key, fb_model, temperature)
        except Overloaded as exc:
            failed.append(name)
            _failover = _next_provider(exc, failed)
