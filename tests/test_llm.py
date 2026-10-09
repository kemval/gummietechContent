"""
llm.py's failover chain, and how gemini.py reads a 429.

The chain is a list so a third free provider is one entry. These run it with
three fakes: on 2026-10-02 Gemini returned 503s all afternoon while Groq's
daily cap was spent, and a third link is what that day wanted.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import gemini
import llm
from llm_errors import Overloaded


def backend(name: str, calls: list[str], overloaded: bool = False,
            keyed: bool = True) -> SimpleNamespace:
    def config():
        if not keyed:
            raise SystemExit(f"{name.upper()}_API_KEY is not set")
        return f"{name}-key", f"{name}-model"

    def generate(prompt, api_key, model, temperature=0.2):
        calls.append(name)
        if overloaded:
            raise Overloaded(f"{name} returned HTTP 503")
        return f"reply from {name}"

    return SimpleNamespace(config=config, generate=generate)


@pytest.fixture
def chain(monkeypatch):
    """Install a primary and fallbacks in llm.py; returns the call log."""
    calls: list[str] = []

    def install(primary, *fallbacks):
        backends = {name: backend(name, calls, **opts)
                    for name, opts in (primary, *fallbacks)}
        monkeypatch.setattr(llm, "BACKENDS", backends)
        monkeypatch.setattr(llm, "PROVIDER", primary[0])
        monkeypatch.setattr(llm, "_backend", backends[primary[0]])
        monkeypatch.setattr(llm, "_failover", None)
        monkeypatch.setattr(llm, "_untried", [f[0] for f in fallbacks])
        return calls

    return install


def test_two_overloaded_providers_fall_through_to_the_third(chain):
    calls = chain(("groq", {"overloaded": True}),
                  ("gemini", {"overloaded": True}),
                  ("github", {}))
    assert llm.generate("p", "k", "m") == "reply from github"
    assert calls == ["groq", "gemini", "github"]


def test_the_switch_is_sticky_for_the_rest_of_the_run(chain):
    calls = chain(("groq", {"overloaded": True}),
                  ("gemini", {"overloaded": True}),
                  ("github", {}))
    llm.generate("p", "k", "m")
    llm.generate("p", "k", "m")
    assert calls == ["groq", "gemini", "github", "github"]


def test_a_fallback_without_a_key_is_skipped(chain):
    calls = chain(("groq", {"overloaded": True}),
                  ("gemini", {"keyed": False}),
                  ("github", {}))
    assert llm.generate("p", "k", "m") == "reply from github"
    assert calls == ["groq", "github"]


def test_every_provider_overloaded_stops_the_run_naming_them(chain):
    chain(("groq", {"overloaded": True}),
          ("gemini", {"overloaded": True}),
          ("github", {"keyed": False}))
    with pytest.raises(SystemExit) as stop:
        llm.generate("p", "k", "m")
    assert "groq then gemini" in str(stop.value)
    assert "No key for github" in str(stop.value)



# ------------------------------------------------------------- openrouter
# Only `:free` ids cost nothing, and its 503 means the account's privacy
# settings rule out every provider — not overload (OpenRouter docs,
# 2026-10-02). Read as overload, it would fail over and hide the cause.

def test_openrouter_refuses_a_model_that_is_not_free(monkeypatch):
    import openrouter_llm
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemma-4-31b-it")
    with pytest.raises(SystemExit) as stop:
        openrouter_llm.config()
    assert ":free" in str(stop.value)


def test_openrouter_503_is_the_privacy_setting_not_overload(monkeypatch):
    import openrouter_llm

    class NoProvider:
        status_code = 503
        text = ""

        def json(self):
            return {"error": {"code": 503, "message": "There is no available "
                              "model provider that meets your routing "
                              "requirements"}}

    monkeypatch.setattr(openrouter_llm.requests, "post",
                        lambda *a, **k: NoProvider())
    with pytest.raises(SystemExit) as stop:
        openrouter_llm.generate("json", "key", "x/y:free")
    assert "privacy" in str(stop.value)


def test_openrouter_is_always_the_last_resort():
    assert llm.FALLBACK_ORDER[-1] == "openrouter"


# ------------------------------------------------------ Gemini's 429 reading
# 46b60ae: a scheduled run stopped on "daily quota is spent" at 16:28 Pacific
# and the next run scored the backlog at 19:14, before any reset. The 429
# matched "per day" in the prose while the violation was per-minute — a
# window backoff clears — and ended the run instead of waiting.


class FakeResponse:
    def __init__(self, status: int, body: dict):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


def quota_429(quota_id: str) -> FakeResponse:
    return FakeResponse(429, {"error": {
        "message": "You exceeded your current quota, which includes the "
                   "per day limit. See the rate-limit docs.",
        "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                     "violations": [{"quotaId": quota_id}]}]}})


OK = FakeResponse(200, {"candidates": [
    {"content": {"parts": [{"text": "scored"}]}}]})


@pytest.fixture
def replies(monkeypatch):
    def install(*queue):
        pending = list(queue)
        monkeypatch.setattr(gemini.requests, "post",
                            lambda *a, **k: pending.pop(0))
        monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    return install


def test_a_per_minute_429_whose_prose_says_per_day_is_waited_out(replies):
    replies(quota_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"),
            OK)
    assert gemini.generate("p", "k", "m") == "scored"


def test_a_per_day_429_still_ends_the_run(replies):
    replies(quota_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    with pytest.raises(SystemExit, match="daily quota"):
        gemini.generate("p", "k", "m")
