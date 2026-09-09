#!/usr/bin/env python3
"""
Selects the pipeline's LLM backend once, so score.py and draft.py don't
each carry a conditional import.

Both callers use the same two-function interface:

    config() -> (api_key, model)
    generate(prompt, api_key, model, temperature=0.2) -> str  (raw JSON text)

gemini.py and groq_llm.py both implement it. This module forwards to
whichever one LLM_PROVIDER names, defaulting to Gemini.

Why a module and not an import line in each caller: LLM_PROVIDER lives in
.env, not the shell, so it has to be read after load_dotenv() but before
the provider module is imported. Doing that in two places invites them to
drift; doing it here keeps the choice in one spot.

CLAUDE.md budget constraint: both providers must stay on their free tier.
Never point this at a paid API — the Groq/Gemini free tiers are the only
sanctioned scoring backends.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# Read .env before deciding which provider module to import.
load_dotenv(REPO_ROOT / ".env")

PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()

if PROVIDER == "groq":
    import groq_llm as _backend
elif PROVIDER in ("", "gemini"):
    PROVIDER = "gemini"
    import gemini as _backend
else:
    sys.exit(f"LLM_PROVIDER={PROVIDER!r} is not a known provider. Set it to "
             "'gemini' or 'groq' in .env, or leave it unset for Gemini.")

# Re-exported so callers can write llm.config() / llm.generate().
config = _backend.config
generate = _backend.generate
