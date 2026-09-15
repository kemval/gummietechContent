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
[1] INGEST → [2] SCORE → [3] DRAFT → [3b] FACT-CHECK → [4] RENDER → [4b] PROOF → [5] HUMAN GATE → [6] PUBLISH
  every 2h    Gemini      LLM         against source    HTML→PNG     the slides   manual          Business Suite
```

Layer 5 is manual and permanent. Do not propose removing it or building
an auto-publish path. It runs over Telegram now (see **The daily run**),
which moves the gate to a phone but does not automate it: the carousel is
still uploaded by hand, and the button only records that it happened.

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
.claude/agents/      fact-check · slide-proof · feed-scout · evergreen-scout
                     (all read-only pre-gate reviewers — see the sections below)
.github/workflows/   ingest.yml (feeds+scoring, 2h) · daily.yml (draft →
                     Telegram, daily) · publish.yml (the publish tap, 15m) ·
                     site.yml (web archive)
src/
  verify_feeds.py    checks every feed URL is live
  ingest.py          feeds → Google Sheets
  llm.py             picks the scoring backend from LLM_PROVIDER
  gemini.py          Gemini request + free-tier retry policy
  groq_llm.py        Groq request, same interface as gemini.py
  score.py           LLM scoring, batched
  draft.py           winning item → paper via Crossref → JSON
  render.py          JSON + template → PNGs
  proof.py           measures the rendered layout — frame, contrast, flag
  site.py            published posts → static web archive
  telegram.py        sends a rendered post for approval; reads the tap back
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

**GitHub Actions on the free tier** delays scheduled runs by 10–30 minutes at
peak and disables scheduled workflows after 60 days of repo inactivity.
Neither matters for a 2-hour cycle, but do not build anything that assumes
punctual execution.

**Feed URLs move constantly.** Never hardcode a URL from memory. Run
`python src/verify_feeds.py -v` after any change to `feeds/`, and treat
that as a required step before wiring a feed into ingest. The `feed-scout`
agent (`.claude/agents/feed-scout.md`) does the legwork — it runs the
checker, finds where a dead feed moved, and proposes the corrected YAML with
evidence — but it only proposes; you still run `verify_feeds.py` and commit.

**`draft.py` drafts from the paper, not the coverage.** Most feeds are news
*about* papers, and coverage inverts mechanisms, overstates what a result
overturns, and quotes whoever gave the interview. So before prompting the
model, `draft.py` scans the fetched page for a DOI — the `citation_doi` meta
tag first, then the first DOI after a journal-reference heading, then any DOI
on the page — and asks Crossref (`api.crossref.org/works/<doi>`, free, no key,
send a contact URL in the User-Agent for the polite pool) who actually wrote
it. The abstract then goes into the prompt as the primary source with the
coverage demoted to context. The middle DOI pass is not decoration: an
aggregator's related-stories rail carries other papers' DOIs. Every step
degrades to coverage-only drafting with a printed warning — a Crossref outage
must never fail a draft.

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

### Proofing the render

`render.py` warns on word count but never looks at the PNGs it produces, and
`hook_size_class()` sizes the hook from its character count, not a measured
layout — so a long compound word, a body field a few words over budget, or a
palette rotation that puts pale ink type on a washed-out field can overflow
the frame, fail contrast, or clip the preprint flag without any error.

`src/proof.py` is the check that runs on every post, including in CI. It
measures rather than looks: every one of those failures is a number in the DOM
of the page `render.py` is about to screenshot, so it reads bounding boxes,
`scrollHeight` and computed colours off the live page and reports
BLOCK / FIX / PASS. It shares `render.py`'s `open_page()` — a layout checked
in a differently-built page is a layout nobody checked.

```bash
python src/proof.py posts/2026-09-15-tides.json      # exits 1 on BLOCK
```

Two measurement choices that are load-bearing:

- **Collisions are tested against line boxes, not element boxes.** The
  element box of a left-aligned block spans the full column even when its
  last line stops short, which made `.source` and `.dots` on slide 5 overlap
  by a constant 3px in a layout where no glyph is near another — it BLOCKed
  all 13 existing posts. Range rects are both quieter there and stricter
  where it matters: a line that really does reach the dots is still caught.
- **The contrast bar is 4.5:1, from this file's own colorway invariant,**
  not WCAG's 3:1 for large text. Chrome (`.domain`, `.wordmark`) is held to
  3.0 instead and only ever reported as FIX, because its `opacity: 0.75` is a
  locked design decision and pink already sits at 3.26:1 — BLOCKing on it
  would fail every post every day. Content type is at full opacity and clears
  4.86:1 at worst, so the strict bar there is real headroom, not luck.

The `slide-proof` agent (`.claude/agents/slide-proof.md`) still exists for
what a measurement cannot answer — whether the slides *look* wrong. Run it
locally on a post that matters. It is read-only: it never edits the JSON or
renders into `output/`, and like `proof.py` it does not check claims or
wording accuracy — that is `fact-check`'s half.

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

`draft.py` resolves the paper and takes `attribution` and `peer_reviewed`
from Crossref, which removes the first two failure modes below at the source.
The agent still checks them, because that resolution is only ever as good as
the DOI it found:

- **Citing the wrong author.** News coverage quotes whoever gave the
  interview — usually the senior (last) author, and sometimes an outside
  commentator who is not an author at all. `attribution` must name the paper's
  first author. Confirm it against Crossref (`api.crossref.org/works/<doi>`)
  rather than the article's prose, and confirm the DOI is the paper the story
  is about rather than one picked up from a related-stories rail.
- **A preprint behind a journal URL.** The `PREPRINT_HOSTS` check in
  `draft.py` sees only the host, so coverage on a news domain reporting
  preprint work slips past it. Crossref's `posted-content` type catches that
  now — but only when a DOI was found at all.
- **A limitation the paper does not state.** This one no code catches.
  `the_catch` is drafted from the abstract, and abstracts do not list
  limitations: those live in the discussion and the appendices. A `the_catch`
  that reads like a plausible caveat rather than a quoted one is the most
  likely thing still wrong on a resolved draft.

A source that cannot be read is a hold, not a pass.

## Drafting output contract

`draft.py` must emit strict JSON, no prose, no code fences:

```json
{
  "post_type": "drop | breakdown | signal",
  "domain": "2-3 word field label, e.g. AI research, materials, astronomy",
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
requirement, not a nicety. When `draft.py` resolves a DOI it builds
`attribution` from the Crossref author list and discards the model's version,
so a wrong attribution on a drafted post means the DOI was wrong, not the
model.

`domain` is required too — it is in `REQUIRED` in `draft.py`, `drop.html`
prints it on every slide, and `ES_FIELDS` translates it. It is a short field
label, not a sentence.

`colorway` is not required. It is validated against `COLORWAYS` and falls
back to `signal` with a warning — a colour that does not suit the topic is a
cosmetic miss, and failing the draft over it would waste the LLM call.

`es` is not part of the contract either. `translate.py` adds it, `render.py`
ignores it — the slides are English only. See **Web archive** below.

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

### Spanish

Every page carries both languages and shows one, toggled by the globe in
the masthead. `site.py`'s `t()` writes each translated string into the DOM
twice and CSS shows the half that `<html data-lang>` names, so switching
needs no second set of pages and no rebuild. The choice is remembered in
`localStorage` and applied before paint, so a reader picks Spanish once and
the whole archive stays Spanish.

The Spanish itself is the post's `es` block, written by `src/translate.py`
from the same free LLM tier as scoring — `ES_FIELDS` in `render.py` lists
the fields, which are exactly the ones a page renders. `caption` and
`hashtags` stay English because Instagram posts in English; `alt_text`,
`<title>` and the meta description stay English because one language has to
win for crawlers and link previews.

Two things that are deliberate:

- **Partial Spanish degrades to none.** A block missing a field is dropped
  whole, with a warning. A reader who gets a Spanish hook over an English
  catch cannot tell a missing translation from a careless one.
- **The toggle is only rendered when the page has Spanish**, and only
  revealed by JavaScript. A button that rearranges the furniture around
  unchanged English advertises an edition the archive does not have.

Machine-written Spanish on a permalink is the same credibility risk as an
unlabelled preprint, so it goes through Layer 5 like everything else: run
`python src/translate.py` and read what it prints **before** adding
`published_at`.

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

## The daily run

`daily.yml` at 12:00 UTC drafts the top-scoring queued row, translates it,
commits the JSON, renders the slides, and sends them to Telegram.
`publish.yml` polls every 15 minutes for the reply. Between them sits a
person, doing what only a person can:

```
daily.yml ─ draft · translate · commit · fact-check · render · proof ─→ Telegram
                                                                          │
                          you read the reports, post the carousel         │
                          to Instagram, tap the button                    │
                                                                          ↓
publish.yml ─ published_at · commit · dispatch site.yml ─→ the archive
```

`src/telegram.py` is both halves — `send` and `confirm` — because both are
the same boundary, and its docstring holds the API-level reasoning. The
constraints that shape it:

- **The slides go as documents, not photos.** `sendPhoto` re-encodes to JPEG
  and downscales past 1280px. The slides are flat colour fields behind a 10px
  border, which is what JPEG bands worst, and they are about to be recompressed
  again by Instagram. Never switch the media group to `photo` to get inline
  previews — Telegram previews a PNG document anyway.
- **The post stem is the only state between the halves,** carried in the
  button's `callback_data` (64 bytes; `slugify` caps a stem at 51). That is
  why `daily.yml` commits the draft *before* sending: `confirm` finds the
  file by name on master.
- **`getUpdates` is called without an offset,** so every tap replays on every
  poll for 24 hours. `confirm` is idempotent against that — it skips a post
  that already has `published_at` — which is what lets it keep no cursor
  between runs. Do not add offset tracking; it would buy nothing and add a
  state file to lose.
- **`publish.yml` dispatches `site.yml` by name.** A push made with
  `GITHUB_TOKEN` does not fire another workflow's `push` trigger;
  `workflow_dispatch` is the documented exception. Removing that line makes
  the archive silently stop updating.
- **`publish.yml` installs `requests` alone,** not `requirements.txt` — it
  runs 96 times a day, and `telegram.py` deliberately does not import
  `render.py`, which would drag in Playwright.

### Both reviews gate the button

`telegram.py send --review FILE` carries each report into the message, and a
report containing `BLOCK` or `UNVERIFIED` withholds the approval button
entirely. That is the gate: a held post cannot be marked live from the phone
at all, rather than arriving with a warning beside a working button.

- **`proof.py`** runs on every post and needs no credentials.
- **`fact-check`** runs as a Claude Code agent through
  `anthropics/claude-code-action`, authenticated with `CLAUDE_CODE_OAUTH_TOKEN`
  from `claude setup-token`. That bills the **Pro subscription, not the API**,
  so it stays inside the $0 rule — but it does draw on the same quota as
  interactive Claude Code sessions, which is why `--max-turns` is capped. The
  agent's read-only contract is held on the runner by a `settings` block that
  allows `Write(/tmp/**)` and denies `posts/` and `src/` outright.
- **No token, no gate change.** With `CLAUDE_CODE_OAUTH_TOKEN` unset the step
  is skipped and the stand-in report says so *without* the gate words, so the
  button behaves as it did before fact-checking existed. A step that was
  configured and then failed writes `UNVERIFIED` instead and does hold the
  post — a check that broke is an unknown, and `fact-check.md` is explicit
  that an unverifiable post is a hold, not a pass.

`GATE_RE` matches `BLOCK` and `UNVERIFIED` case-sensitively on word
boundaries, so `fact-check.md`'s own prose about "a block page" does not trip
it. A summary line like "0 BLOCK" would, and that is the right direction to
be wrong in: the cost is opening the report.

Nothing gates a **local** `send` with no `--review` flags — the message says
plainly that nothing checked the post, but the button still appears, because
a person sending by hand is already in the loop.

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
