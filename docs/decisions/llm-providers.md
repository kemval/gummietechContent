# LLM providers: batching, limits, failover

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**Batch LLM scoring 15–20 items per request.** Gemini's free tier has a daily
request cap as well as a per-minute one. One request per item would exhaust
the daily cap; batching drops it to 20–30 calls a day. Add a keyword
pre-filter in Python (drop "raises $", "Series A", "announces partnership")
before anything reaches the LLM.

**Gemini free tier limits** are roughly 10–15 requests/minute with a daily cap
that varies by model. Limits apply per project, not per key. Daily quotas
reset at midnight Pacific. Handle 429s with exponential backoff; fail fast on
daily-cap errors since backoff will not help.

**Swapping to Groq** is `LLM_PROVIDER=groq` in `.env` (or the repo variable in
CI) plus `GROQ_API_KEY`. `llm.py` forwards `score.py` and `draft.py` to
`groq_llm.py`, which mirrors `gemini.py`'s two-function interface. Groq's free
tier has the same per-minute + per-day shape, but its 429 body is plain prose,
not Gemini's structured `QuotaFailure` — so the daily-vs-per-minute split in
`groq_llm.py` is a best-effort text parse and is flagged as unverified in the
code. Confirm it against a real daily-cap response before relying on it in CI.

**The two providers fail over for each other.** Gemini's shared free-tier
capacity sheds load with 503s often enough to kill a whole run on its first
batch — it took out four of eight scheduled ingests on 14–15 Sep 2026. So when
the provider `LLM_PROVIDER` names returns 5xx on every retry, `llm.py` switches
to the other one for the rest of the process and prints the switch. It needs
both keys present to do it; with only one, the run ends as it did before, and
the error says which key was missing. Three deliberate limits:

- **Only 5xx exhaustion fails over.** A rejected key or a retired model is a
  configuration error that wants fixing, not routing around. A spent daily cap
  could fail over in principle, but quietly sending a day's scoring to the
  other provider would hide the cap and spend the budget `draft.py` needs.
  Those all still stop the run where they happen.
- **The switch is sticky** for the life of the process: an overload window
  outlives one request, so retrying the dead provider on every batch would
  spend the job's 15-minute timeout on backoff and land in the same place.
- **`llm_errors.Overloaded` is what carries it.** Both providers raise it
  instead of `SystemExit` when 5xx outlasts `MAX_RETRIES`; `llm.py` turns it
  back into `SystemExit`, message intact, when there is nothing to switch to.
  It sits in its own module because `llm.py` imports both providers, so
  defining it there would be an import cycle.
