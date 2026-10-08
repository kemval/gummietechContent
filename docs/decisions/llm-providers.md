# LLM providers: batching, limits, failover

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**Batch LLM scoring 15–20 items per request.** Gemini's free tier has a daily
request cap as well as a per-minute one. One request per item would exhaust
the daily cap; batching drops it to 20–30 calls a day.

**Measured 2026-10-08, that estimate was half the real load.** Weekdays
ingest 650–1,200 rows, which is 37–68 scoring calls at `BATCH_SIZE` 18.
Weekends are about 5. Drafting, translating and retries add a handful, so a
heavy day is about 80 requests. Google no longer publishes the free tier's
daily cap: the rate-limits page points to each project's own AI Studio
dashboard. Read there on 2026-10-08:

| model | RPM | TPM | RPD |
|---|---|---|---|
| Gemini 3.5 Flash (`gemini.DEFAULT_MODEL`), and every other "Flash" | 5 | 250K | **20** |
| Gemini 3.5 Flash Lite, 3.1 Flash Lite | 15 | 250K | **500** |
| Gemma 4 31B | 30 | 16K | 14.4K |

So Gemini 3.5 Flash cannot carry production: a weekday needs two to four
times its daily cap. On 2026-10-08 `LLM_PROVIDER` was set to gemini for a
few hours, and the project went to 24/20 the same day. It went back to
groq, and a dispatched ingest scored 36 of 36. Third-party figures for the
cap (about 1,500, or about 100 after an April cut) were both wrong for this
account, so read it from the dashboard. Gemini 3.5 Flash Lite at 500 a day
is the candidate for scoring, to be measured against the current scores
first; the workflows do not pass `GEMINI_MODEL` today. A spent daily cap stops
the run; it does not fail over (see below). Add a keyword
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

**The chain, and the third link that was not (2026-10-02).** That afternoon
Gemini returned 503s on every attempt while Groq's `gpt-oss-120b` daily cap
(200k tokens) had been spent by a one-off relabel that had itself failed over
from Gemini — so there was nothing to draft with. `llm.py` now walks
`FALLBACK_ORDER` after the primary, skipping any fallback whose key is
missing, so a third provider is one module and one entry. GitHub Models was
added as that third link and removed the same day: its first live call
returned HTTP 200 with a plain-text `OK` body, because GitHub had retired
the service on 2026-07-30 (closed to new customers 2026-06-16). The endpoint
had come from search results, not GitHub's docs — read the provider's own
docs and changelog before building against it.

**OpenRouter is the third link (2026-10-02).** Its `:free` models need no
card: 20 requests a minute and 50 a day across all of them (1,000 needs a
one-time $10 purchase, which the $0 rule rules out). `openrouter_llm.py`
refuses any model id not ending in `:free`, so a typo cannot reach a paid
model. Three things its docs say that shaped the code:

- The free list rotates — "less popular models will soon transition away
  from the free tier" — so the model is the `OPENROUTER_MODEL` repo
  variable. The default is `nvidia/nemotron-3-super-120b-a12b:free`, which
  answered a live draft with valid JSON on 2026-10-02. `google/gemma-4-31b-it:free`,
  tried first, returned 429 "Provider returned error" on every attempt: a free
  model's upstream provider is shared by every OpenRouter user.
- Most free endpoints are served by providers that may log prompts, and are
  only routed to once the account's privacy settings allow it. The prompts
  are public news and papers, so it was allowed on 2026-10-02.
- Its 503 means "no available model provider that meets your routing
  requirements" — configuration, so it stops the run with that hint. Its
  502 ("your chosen model is down") is the overload that fails over.

**Cerebras was considered and rejected** under the $0 rule: its developer
tier needs a payment method and is a one-time $5 credit, after which access
pauses — a fallback that quietly stops existing a month later. OpenRouter took the slot instead.

**Spending a shared cap from a laptop.** A local run reads the same keys as
CI, so a long one-off job (a relabel, a re-translation) that fails over to
Groq spends the quota the scheduled runs need. Pin a one-off to one provider
by blanking the others' keys for that command, e.g.
`LLM_PROVIDER=gemini GROQ_API_KEY= python src/score.py …`.
