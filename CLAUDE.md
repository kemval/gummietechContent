# CLAUDE.md — gummietech pipeline

Instructions for Claude Code working in this repo.
Content strategy, source lists, and post formats live in
`docs/gummietech_content_system.md` — read it when the task touches
what gets posted rather than how the pipeline runs.

---

## What this repo is

An automated content pipeline for @gummietech, an Instagram account
publishing science, technology, and engineering posts. It ingests RSS
feeds, scores items with an LLM, drafts post copy as JSON, renders that
JSON to PNG slides, and queues them for human approval.

```
[1] INGEST → [2] SCORE → [3] DRAFT → [3b] FACT-CHECK → [4] RENDER → [5] HUMAN GATE → [6] PUBLISH
  every 2h    Gemini      LLM         against source    HTML→PNG     manual          Business Suite
```

Layer 5 is manual and permanent. Do not propose removing it or building
an auto-publish path.

## Budget: $0/month — hard constraint

Every dependency must be free tier, open source, or self-hosted at no cost.
Never add a paid service. When the obvious tool costs money, find the free
route: open-source equivalent, first-party alternative, or write the code
that replaces the service.

Two things this does not mean:

- **Do not claim something is free when it is not.** Verify current terms
  when it matters. Say plainly when a feature is paid-only and route around it.
- **Do not hide real limits.** State caps and rate limits up front so they can
  be designed around, then proceed. Naming a constraint is not refusing.

**Claude Code usage and pipeline runtime LLM calls are separate budgets.**
Claude Code is covered by the user's Pro plan. Production scoring must stay on
Gemini or Groq free tiers — never point `ingest.py` or `score.py` at a paid API.

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Ingest | `feedparser` + `requests` |
| Scheduler | GitHub Actions cron |
| Database | Google Sheets (`gspread`) |
| LLM scoring | Gemini free tier (Flash), or Groq free tier — `LLM_PROVIDER` |
| Rendering | Playwright → PNG |
| Templating | Jinja2 |
| Config | YAML feed lists, `.env` for secrets |

## Layout

```
.claude/agents/      fact-check.md — verifies a draft against its source
.github/workflows/   GitHub Actions cron
src/
  verify_feeds.py    checks every feed URL is live
  ingest.py          feeds → Google Sheets
  llm.py             picks the scoring backend from LLM_PROVIDER
  gemini.py          Gemini request + free-tier retry policy
  groq_llm.py        Groq request, same interface as gemini.py
  score.py           LLM scoring, batched
  draft.py           winning item → JSON
  render.py          JSON + template → PNGs
  site.py            published posts → static web archive
feeds/               *.yaml source lists by tier
posts/               drafted post JSON
templates/
  tokens.css         the locked palette and type stack — included by both
  drop.html          production slide template — 1080x1350
  site_base.html     web archive shell; index.html and post.html extend it
output/              rendered PNGs (gitignored)
site/                built web archive (gitignored)
docs/                strategy reference
```

## Non-obvious constraints — read before writing code

**Fetch feeds with a browser User-Agent.** Publishers behind Cloudflare return
403s or HTML block pages to unfamiliar agents, and feedparser reports the
latter as a confusing "not well-formed" XML error rather than a network
failure. `src/verify_feeds.py` has working headers — reuse them everywhere
a feed is fetched.

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

**GitHub Actions on the free tier** delays scheduled runs by 10–30 minutes at
peak and disables scheduled workflows after 60 days of repo inactivity.
Neither matters for a 2-hour cycle, but do not build anything that assumes
punctual execution.

**Feed URLs move constantly.** Never hardcode a URL from memory. Run
`python src/verify_feeds.py -v` after any change to `feeds/`, and treat
that as a required step before wiring a feed into ingest.

**Secrets** go in `.env` locally and GitHub Actions repo secrets in CI.
Never commit `.env`, `credentials.json`, or any key.

## Rendering

Slides render at **1080×1350** (4:5). Each slide is a `.slide` div with a
unique id inside `templates/drop.html`; screenshot each individually with
Playwright rather than capturing the page.

Design tokens are locked — do not change them or propose alternatives.
They live in `templates/tokens.css`, which both `drop.html` and
`site_base.html` include, so the slides and the web archive cannot drift
apart. Do not copy these values into a third place:

```css
--pink:  #EE6EC0;   /* field */
--olive: #B2BC5F;   /* field */
--cream: #F7EFE2;   /* neutral field, always slide 2 */
--ink:   #3B2C23;   /* outline + type, not black */
--blush: #F9A8D4;   /* field, sparing */
--sky:   #7FB2E5;   /* field */
--amber: #F2B441;   /* field */
```

Type: Outfit 800 for display, Figtree 500/700 for body, both Google Fonts.
Signature element: a 10px `--ink` border, 44px radius, inset 34px from the
canvas edge, on every slide.

### Colorways

The hues rotate per post; the *rhythm* is what is fixed. Never hardcode a
field colour in the template — address colour by role (`--field`,
`--on-field`, `--frame`, `--flag-bg`/`--flag-fg`) and let the modifier class
set the hue, or the dark slide breaks the moment the palette rotates.

`COLORWAYS` in `src/render.py` is the single source of truth. Each family is
a `(lead, support)` pair, and every post renders
`lead · cream · support · dark · lead`:

| family | topics | lead | support |
|---|---|---|---|
| `signal` | AI, computing, software, robotics | pink | olive |
| `orbit` | space, astronomy, physics | sky | pink |
| `bloom` | biology, medicine, climate, ecology | olive | blush |
| `ember` | energy, materials, engineering, chemistry | amber | pink |

Invariants that keep the grid recognizable, and that a new family must respect:

- `--ink` is the type, the frame and the dots on every light slide.
- Slide 2 is always `--cream` — the rest slide.
- Slide 4 (the catch) always drops to `--ink`; its frame and preprint flag
  carry the post's lead hue.
- Slides 1 and 5 share a field — the hook and CTA bookend the post.
- A new lead or support hue must clear 4.5:1 against `--ink`.

`draft.py` picks the family and `render.py` resolves it, so an invented name
falls back to `signal` with a warning rather than reaching the CSS.
`render.py --colorway <name>` overrides the JSON at the human gate.

## Fact-checking a draft

`draft.py` drafts from the feed summary when the publisher blocks the article
fetch, and the model then writes fluent, plausible, wrong slides. Run the
`fact-check` agent (`.claude/agents/fact-check.md`) on a post before rendering
it — it re-fetches `source_url`, finds the paper behind the news coverage, and
checks each slide claim against it, reporting BLOCK / FIX / PASS with the
supporting sentence.

It is read-only by design: it reports, and a person applies the edits. Do not
give it Edit or Write, and do not let it add `published_at`. Layer 5 is the
point.

Two failure modes it exists to catch, because nothing in code can:

- **Citing the wrong author.** News coverage quotes whoever gave the
  interview, who is usually the senior (last) author. `attribution` must name
  the paper's first author. Confirm the order against Crossref
  (`api.crossref.org/works/<doi>`) rather than the article's prose.
- **A preprint behind a journal URL.** The `PREPRINT_HOSTS` check in
  `draft.py` sees only the host, so coverage on a news domain reporting
  preprint work passes it while being wrong.

A source that cannot be read is a hold, not a pass.

## Drafting output contract

`draft.py` must emit strict JSON, no prose, no code fences:

```json
{
  "post_type": "drop | breakdown | signal",
  "colorway": "signal | orbit | bloom | ember",
  "hook": "",
  "what_happened": "",
  "why_it_matters": "",
  "the_catch": "",
  "caption": "",
  "keywords": [],
  "hashtags": [],
  "alt_text": "",
  "source_url": "",
  "attribution": "",
  "peer_reviewed": true
}
```

`attribution` and `alt_text` are required. `render.py` should refuse to
render a record missing either — attribution is a legal and reputational
requirement, not a nicety.

`colorway` is not required. It is validated against `COLORWAYS` and falls
back to `signal` with a warning — a colour that does not suit the topic is a
cosmetic miss, and failing the draft over it would waste the LLM call.

`published_at` is not part of the contract and `draft.py` never emits it. It
is added by hand, as `YYYY-MM-DD`, when the post actually goes live on
Instagram, and it is the only thing that lets a post onto the public archive.
`render.py` ignores it. See **Web archive** below.

When `peer_reviewed` is false, the template must show the
"Preprint — not yet peer-reviewed" flag. Enforce this in code, not by
convention.

## Code style

- Complete working files, not fragments.
- Type hints on function signatures.
- Every network call wrapped with explicit timeout and error handling.
- Error messages say what to do next, not just what failed.
- Standard library where it suffices; no dependency for twenty lines of code.
- Comment the non-obvious constraints above wherever they appear in code,
  since they are invisible failure modes otherwise.

## Web archive

`src/site.py` builds `posts/*.json` into a static site — an index plus one
page per carousel — deployed to GitHub Pages by `.github/workflows/site.yml`
at <https://kemval.github.io/gummietechContent/>. That URL is the Instagram
bio link.

It exists because Instagram does not make caption URLs clickable. `draft.py`
records `source_url` and `render.py` writes it into `caption.txt`, but slide 5
can only print `attribution` as flat text, so without this the source never
reaches a reader.

Two rules:

- **It is not a blog.** Every page is a pure function of the draft JSON. Do
  not add a field that requires writing prose per post — that is a second
  content product, and the time for it does not exist.
- **`published_at` is the human gate.** `draft.py` writes into `posts/` before
  approval, so `site.py` skips any post without that date. Do not add a
  fallback that publishes undated posts. Layer 5 applies to the web too, and a
  wrong post on a permalink is worse than a wrong post in a feed.

`site.py` skips a malformed post with a warning instead of exiting — the
opposite of `render.py`, which is right to hard-fail the one post it was asked
to render. One bad draft must not take the whole site down.

## Publishing

Meta Business Suite Planner, manually, is the current path. It is free,
first-party, supports carousels, and has no post cap.

The Instagram Graph API is a later option: free but gated by app review,
requires a Professional account linked to a Facebook Page, uses a two-step
container + publish call, has **no native scheduling endpoint**, and caps at
50 API-published posts per rolling 24 hours. Do not start building against it
without an explicit decision.

## When updating strategy

`docs/gummietech_content_system.md` and this file both describe the project
and can drift. If a change here affects strategy — or vice versa — say so
rather than silently updating one.
