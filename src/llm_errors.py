#!/usr/bin/env python3
"""
The one error the provider modules raise and llm.py acts on.

It lives in its own module rather than in llm.py because gemini.py and
groq_llm.py have to raise it and llm.py imports them: defining it there
would make the import a cycle. Both providers are peers, so neither can
own it for the other either.
"""

from __future__ import annotations


class Overloaded(RuntimeError):
    """
    The provider returned 5xx on every retry — its shared capacity is
    shedding load, not our request being wrong.

    Distinct from SystemExit on purpose. Everything else a provider gives
    up on (a rejected key, a retired model, a spent daily cap) is a
    condition the other provider should not paper over, so those still
    stop the run where they happen. This one llm.py can answer by
    switching providers, and turns back into SystemExit — carrying this
    exception's message — when it cannot.
    """
