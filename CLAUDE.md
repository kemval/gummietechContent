# CLAUDE.md — gummietech pipeline

Instructions for Claude Code working in this repo.
Content strategy, source lists, and post formats live in
`docs/gummietech_content_system.md` — read it when the task touches
what gets posted rather than how the pipeline runs. The second pillar, the
daily status-report slide, has its own: `docs/gummietech_status_reports.md`.

---

## What this repo is

An automated content pipeline for @gummietech, an Instagram account
publishing science, technology, and engineering posts. It ingests RSS
feeds, scores items with an LLM, drafts post copy as JSON, renders that
JSON to PNG slides, and queues them for human approval.

```
[1] INGEST → [2] SCORE → [3] DRAFT → [3b] FACT-CHECK → [4] RENDER → [4b] PROOF → [5] HUMAN GATE → [6] PUBLISH → [7] LEARN
  every 2h    Gemini      LLM         against source    HTML→PNG     the slides   manual          Business Suite   saves/shares
```

Layer 5 is manual and permanent. Do not propose removing it or building
an auto-publish path. It runs over Telegram now (see **The drafting run**),
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
.github/actions/     notify-failure (one definition of "this run broke",
                     called by every scheduled workflow) · resolve-post
                     (one definition of "the post that is waiting")
.github/workflows/   check.yml (on push: the offline half, no secrets) ·
                     ingest.yml (feeds+scoring, 2h) · daily.yml (draft →
                     commit, Mon/Wed/Fri) · review.yml (fact-check · render
                     · proof · send — called, never scheduled) · recheck.yml (run
                     review.yml again on a held post) · fix.yml (apply the
                     fact-check to a held post, then review.yml again) ·
                     publish.yml (the publish tap, 15m) · site.yml (archive) ·
                     watch.yml (daily: is any of this still running?) ·
                     series.yml (the status-report pillar, daily)
src/
  formats.py         what each carousel format is made of — the one table
  verify_feeds.py    checks every feed URL is live
  ingest.py          feeds → Google Sheets
  llm.py             picks the scoring backend from LLM_PROVIDER
  gemini.py          Gemini request + free-tier retry policy
  groq_llm.py        Groq request, same interface as gemini.py
  score.py           LLM scoring, batched
  draft.py           winning item → paper via Crossref → JSON;
                     --signal walks five rows for the weekly roundup
  render.py          JSON + template → PNGs
  proof.py           measures the rendered layout — frame, contrast, flag
  site.py            published posts → static web archive
  series.py          the status-report pillar — what is queued, what went
                     out, in what order; `python src/series.py` prints it.
                     Not a post_type; see below
  telegram.py        sends a rendered post for approval; reads the tap back,
                     and asks a settled post for its Instagram numbers
  learn.py           the metrics report — what to cut, what to double
  watch.py           the daily audit — what did not happen and should have
feeds/               *.yaml source lists by tier
series/              reports/*.json + images/*.png — the status-report pillar
tests/               pytest over the pure functions; every case is a
                     post-mortem — see **When something breaks**
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

**It also does not honour a high-frequency cron, and a cron is a request
rather than a promise.** `publish.yml` asks for `*/15 * * * *` and gets
roughly one run every two hours: measured on 2026-09-20, eight runs across
19.5 hours — 06:04, 10:52, 14:01, 17:15, 19:24, 21:31, 23:30, 01:36 UTC.
Read every "every 15 minutes" in this file as "a handful of times a day, on
GitHub's terms". What that changes: a tap is recorded within a couple of
hours rather than minutes, and anything rate-limited to one per poll drains
about eight times slower than the cron suggests. What it does not change:
nothing here is correctness-dependent on the interval — `confirm` is
idempotent, and a tap replays for 24 hours whatever the cadence.

**A once-a-day cron is not shed, it is delivered hours late — a different
failure with a different fix.** `daily.yml` has been honoured every single
time it asked (5/5 as of 2026-09-21) and never once near the minute it asked
for: a 12:17 UTC cron ran at 17:04, 17:04, 16:29, 15:55 and 18:12, between
3h38m and 5h55m late. `created_at` equals `run_started_at` on all five, so
this is the scheduler firing late rather than a run queueing behind a busy
runner. Do not confuse the two shapes: a `*/15` cron loses most of its
firings and keeps its punctuality, a daily cron keeps all of them and loses
its hour.

What it cost: on 2026-09-21 the Monday Drop reached Telegram at 12:15 local
against a comment promising 06:30, which reads as a broken pipeline rather
than a late one — nothing had failed, and no alert fires for a run that
simply has not started yet. `notify-failure` speaks for broken runs; it
cannot speak for absent ones, because a run that has not been created has no
runner to speak from. Nothing did, until `watch.yml` — a *different* run,
once a day, looking backwards at what the pipeline left behind. See
**Watching the pipeline**.

Since you cannot ask GitHub for less delay, only for an earlier hour,
`daily.yml` asks four times — `17 6,8,10,12 * * 1,3,5` — and its `gate` job
makes every firing after the first a no-op by asking whether `posts/` already
holds a post dated today. The worst case is the old behaviour; the best case
is a message waiting before the day starts. Any workflow that must land near
a particular hour needs the same shape. Do not tighten the interval instead:
that is the `*/15` mistake, and it buys shedding on top of lateness.

**The runner is pinned to `ubuntu-24.04`, and `ubuntu-latest` is the bug.**
GitHub moves that label to Ubuntu 26.04 *gradually*, between 19 Oct and
19 Nov 2026 (`actions/runner-images#14748`), and gradual is the worst shape
for an unattended pipeline: for a month some runs would take one image and
some the other, so a break would come and go and read as a flake rather than
as a change. The exposure is not Python — `setup-python` pins 3.12 whatever
the image is — it is `playwright install --with-deps chromium` in `check.yml`
and `review.yml`, which apt-installs a library list that is per-release, on
an image whose kernel and systemd both move (6.17→7.0, 255.4→259.5). Twelve
jobs carry the label and Actions gives no way to write it once, so each one
says why in a line rather than leaving twelve bare literals for someone to
"modernize" back. Unpin deliberately — a green `check.yml` on `ubuntu-26.04`
first, then all twelve — rather than by tidying the comment away.

**Feed URLs move constantly.** Never hardcode a URL from memory. Run
`python src/verify_feeds.py -v` after any change to `feeds/`, and treat
that as a required step before wiring a feed into ingest. The `feed-scout`
agent (`.claude/agents/feed-scout.md`) does the legwork — it runs the
checker, finds where a dead feed moved, and proposes the corrected YAML with
evidence — but it only proposes; you still run `verify_feeds.py` and commit.

**And a feed can be live and finished at the same time.** A publication that
stops does not take its feed down: the URL answers 200 for years and
feedparser returns a full item list, so every question of the form "did
entries come back" says yes. What changes is downstream — `ingest.py` drops
each of those items on `MAX_AGE_DAYS`, so the feed contributes no rows at
all. SemiAnalysis was wired into `feeds/tier5_depth.yaml` on 2026-09-22 on
the strength of a clean OK and 10 entries, none newer than Sep 2025, and only
a dry-run ingest caught it. Both checks now measure the newest entry's age
against `verify_feeds.STALE_AFTER_DAYS`: the checker prints it and marks
anything past the bar, and `watch.py` reports it as a FIX. The bar is 60 days
rather than `MAX_AGE_DAYS`' 7 because `watch.py` sends to a chat and a
watcher that cries wolf is one nobody reads — measured over all 65 feeds that
day, the live set ran median 0d, p90 5d, max 7d, and the dead ones 215d, 371d
and 609d. An undated feed has no age and is never reported, which is
`ingest.py`'s own decision about undated rows one layer up.

**The queue is deduplicated by URL, and a story is not a URL.** Many feeds
cover one press release; each copy is its own row with its own score, and
the siblings of the row that gets drafted stay queued forever. On
2026-09-17 the top row of the queue was the paper published that same
morning. So `draft.py` resolves each candidate's paper *before* the LLM call
and skips a row whose DOI or Crossref citation already appears in `posts/`,
marking it `duplicate` in the sheet. It gives up after `MAX_DUPLICATE_SKIPS`
fetches rather than walking the queue inside a 15-minute job. A candidate
named by hand — `--row`, `--url`, an evergreen brief — warns and drafts
anyway, because naming one is the override. Coverage with no resolvable DOI
cannot be matched at all: that is the `fact-check` agent's step 8, which reads
`posts/` and can see what a key cannot. `feeds/tier5_depth.yaml` is a whole
tier of that case — essays have no DOI, so nothing about them is deduplicated
and `attribution` and `peer_reviewed` both come from the model rather than
from Crossref. The feed file's header says what that costs; it is the reason
that tier is two feeds and not twenty.

**The duplicates are cross-headline, which is why the DOI is the only key
that finds them.** This file used to say forty-five feeds carry one press
release into a queue of 1440 rows. Measured on 2026-09-21, both numbers were
wrong and the shape they implied was wrong with them:

| | said | measured |
|---|---|---|
| rows in the sheet | 1440 | 4864 — 1383 `queued`, 3044 `rejected`, 24 `drafted` |
| copies of one story | ~45 | largest title-group 3; 56 of 57 groups are pairs |

Outlets rewrite the headline. Phys.org, EurekAlert, ScienceDaily and the
university newsrooms each write their own, so the copies do not look alike
as strings even when they report the same paper. Grouping the whole sheet by
normalised title finds 57 stories with more than one row and would retire 58
rows, 22 of them `queued` — 1.6% of the queue. Probed the other way round,
sixteen of the 24 rows already drafted have no other row in all 4864 that
shares even three content words. A pair that really is one story scores
0.27:

```
"Ancient proteins identify various Denisovan remains from Southwest China"
"First Denisovan forearm bone discovered in southwest China"
```

So **do not rebuild title-based deduplication in front of `score.py`.** It
was written, tested and measured on 2026-09-21 and then removed: it buys
about 1% of the LLM quota, it cannot see the duplicates that actually reach
the gate, and loosening it to catch them starts merging stories that are
merely adjacent long before it catches them — at a Jaccard bar of 0.35, still
too high to pair the two lines above, the largest group is already 17.
Lowering `MAX_DUPLICATE_SKIPS` on the strength
of a title pass would be the same mistake wearing a different hat. The paper
is the identity; `resolve_paper` is what recovers it, and paying a fetch per
candidate is what that costs.

One consequence for strategy: `docs` §Layer 2's fifth automatic reject —
"anything already covered by three or more large accounts" — is absent from
`score.PROMPT` because a model reading one headline cannot know it, and the
sheet cannot cheaply tell it either. It stays unimplemented, and that is a
measurement rather than an oversight.

**The sheet grows forever, and that is fine — do not build a purge.** Nothing
deletes a row, so `rejected` accumulates: 3044 of 4864 rows on 2026-09-21.
Measured the same day, the growth costs nothing worth code. `get_all_values()`
over the whole sheet takes 0.77s; 48,650 cells of the 10,000,000 a spreadsheet
allows; ~247 rows a day, which reaches that ceiling somewhere around 2037.

The reason not to purge is sharper than the reason not to bother.
**`rejected` rows are the deduplication memory.** `ingest.existing_urls()`
reads the whole `url` column and drops anything already there, so deleting a
rejected row does not free a row — it re-ingests the item on the next cycle
and pays `score.py` to reject it again. That trades storage, which is free
and effectively unbounded, for the free tier's daily request cap, which is
the one budget in this pipeline that actually binds.

Two facts about the sheet worth knowing before measuring anything on it.
Rows 1331-1737 are 407 completely empty rows, left by a write that went
wrong; they are inert, since `score.py` looks for `new` and `draft.py` for
`queued`. And because of them a naive count of repeated `url` values reports
406 duplicates where there are none at all — the empty string, counted 407
times. Deduplication has never let one through.

If a purge is ever genuinely needed, the only safe rule is age: a row whose
`published` is older than `MAX_AGE_DAYS` cannot come back, because
`ingest.py` would drop it on age even if the feed still lists it. Undated
rows are never safe — `ingest.py` keeps them on purpose, so they have no age
to test and would return immediately.

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

Slides render at **1080×1350** (4:5). Each slide is a `.slide` div inside the
template its `post_type` names — `templates/<post_type>.html`, falling back to
`drop.html` with a warning; screenshot each individually with Playwright
rather than capturing the page.

**How many slides a format has is the template's business.** `render.py`
discovers them with `querySelectorAll('.slide')` in document order rather than
listing ids, so adding a format is adding a template. It refuses a template
rendering fewer than `MIN_SLIDES` (4): below that there is nowhere to put the
bookends, the rest slide and the catch.

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
a `(lead, support)` pair, and a five-slide Drop renders
`lead · cream · support · dark · lead`:

| family | topics | lead | support |
|---|---|---|---|
| `signal` | AI, computing, software, robotics | pink | olive |
| `orbit` | space, astronomy, physics | sky | pink |
| `bloom` | biology, medicine, climate, ecology | olive | blush |
| `ember` | energy, materials, engineering, chemistry | amber | pink |

Invariants that keep the grid recognizable, and that a new family or a new
format must respect. `render.rhythm()` is these rules as code, which is why a
longer format needs no new palette decision:

- `--ink` is the type, the frame and the dots on every light slide.
- Slide 2 is always `--cream` — the rest slide.
- **The catch is the second-to-last slide** and always drops to `--ink`; its
  frame and preprint flag carry the post's lead hue. `proof.py` finds it by
  its field rather than by its id, because it is slide 4 of a Drop and some
  other number of a Breakdown.
- **The first and last slides share a field** — the hook and CTA bookend the
  post.
- Everything between the rest slide and the catch alternates support and
  lead. A longer format only ever extends that middle, which is the only part
  it adds.
- A new lead or support hue must clear 4.5:1 against `--ink`. `tests/` asserts
  this for all five current hues rather than trusting it.
- **No two consecutive posts share a field.** `rhythm()` refuses to put the
  same hue on two neighbouring slides; `render.vary()` is that rule one level
  up, between posts. Topic alone cannot hold it: a science feed clusters, and
  four families divided among everything published means neighbours collide
  often. On 2026-09-18, 09-19 and 09-20 the topics were materials, biohybrid
  robotics and applied thermodynamics — all `ember` — and three amber posts
  shipped in a row while every mapping worked exactly as documented.

`vary(chosen, previous)` returns `chosen` untouched unless the post before it
already had that family, in which case it takes the next family in
`COLORWAYS` order — deterministic, so a re-render of an approved post cannot
come back a different colour, and guaranteed to differ from `previous`
because it only ever runs when the two are equal. The topic keeps its own
family in the ordinary case; the rule only fires on a collision.

`previous_colorway()` answers what "before" means, and it is strictly the
predecessor rather than the newest other post: a post being re-rendered sits
in `posts/` with successors after it, and answering with one of those would
compare it against a post nobody has seen yet. `post_order()` is the order a
reader meets them — `published_at` when there is one, the filename's date
when there is not, so a drafted-but-ungated post sits where it will land. Both
skip `posts/era*.json` by the same date-prefix filter `resolve-post` needs.

`draft.py` applies this to what it writes. A Breakdown is written by hand and
never passes through it — 2026-09-20's was the third amber post for that
reason — so `render.py` warns at render time when a post repeats its
predecessor and names the `--colorway` that breaks the run. It warns rather
than rewrites: `render.py` renders the record it was given.

`draft.py` picks the family and `render.py` resolves it, so an invented name
falls back to `signal` with a warning rather than reaching the CSS. A template
asks for its own rhythm with `{% set fields = rhythm(5) %}`: the template is
what knows how many slides it has, `render.py` is what knows what colour they
go in, and neither has to be edited when the other changes.
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

Three measurement choices that are load-bearing:

- **What gets measured is decided by shape, not by a list of class names.**
  It used to be a CSS selector naming every class, and a template with new
  ones was simply not measured: `templates/signal.html` shipped its credit
  line overlapping the wordmark by 18px on five slides, and a rank numeral
  at 1.5:1, and this file reported PASS. Now every element inside the frame
  that carries text and has no texted children is measured, so a new format
  is covered without anyone remembering to register it. `CHROME` is still a
  list, and that is fine: a class missing from *it* is merely held to the
  stricter bar and says so loudly. Silence is the failure worth engineering
  against.

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

**It also carries the one rule that is not about this post's pixels.**
`check_colorway()` reports a post that repeats its predecessor's field, as a
FIX. `render.py` already says this, to a run log nobody reads at the gate;
this report is carried into the Telegram message, which is the last place the
rule can still be acted on — after approval the post is on the grid. A
record-level check in a file that otherwise measures the DOM, for the reason
`check_words()` is one. FIX and not BLOCK because a repeated hue is cosmetic,
and withholding the button over one teaches a person to tap "Posted anyway"
without reading. It skips a path outside `post_order()`: the `era*.json`
fixtures are not posts, and `previous_colorway()` treats a path it cannot
find as arriving at the end of the archive, which made every fixture report
as clashing with the newest real draft.

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

It is read-only by design: it reports, and something else applies the edits.
Do not give it Edit or Write, and do not let it add `published_at`. Layer 5 is
the point.

What applies them is `fix.yml`, tapped from the chat — a separate Claude Code
session that reads the report and writes the JSON, so that the checker is never
marking its own homework. It may edit one post file and nothing else, it may
not add `published_at`, and a guard step on the diff enforces both rather than
trusting the prompt. Its output then goes back through `review.yml` for a fresh
fact-check that never saw it. See **The drafting run**.

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

`doi` is not part of the contract either: `draft.py` writes it when Crossref
resolved the paper, so `covered_papers()` can tell whether a queued row is a
story already posted. The model never supplies it, and `render.py` ignores it.

`domain` is required too — it is in `REQUIRED` in `draft.py`, `drop.html`
prints it on every slide, and `ES_FIELDS` translates it. It is a short field
label, not a sentence.

`colorway` is not required. It is validated against `COLORWAYS` and falls
back to `signal` with a warning — a colour that does not suit the topic is a
cosmetic miss, and failing the draft over it would waste the LLM call.

`es` is not part of the contract either. `translate.py` adds it, `render.py`
ignores it — the slides are English only. See **Web archive** below.

**The body fields above are the Drop's.** `post_type` decides which set a
record carries, and `src/formats.py` is the one table that says so — a
Breakdown wants `the_question`, `the_intuition` and a `mechanism` list
instead of `what_happened`, and an optional `recap`. It shares
`why_it_matters` and `the_catch` with the Drop rather than inventing
synonyms: the job of those two slides is identical, and sharing the names is
what lets `site.py`, `translate.py` and the gate treat every format the same.

**A Signal does not fit that shape at all, and the table says so.** It is
five items with five sources, so `attribution`, `source_url` and
`peer_reviewed` are properties of an entry rather than of the post — §7.3
makes credit mandatory per source and §7.2 makes the preprint label
mandatory, and one of five carrying them satisfies neither. `Format.entries`
lists what each item must have and `missing_from_entries()` names the one
that is short. Two consequences worth knowing before touching it:

- **`peer_reviewed` is tested for presence, not truth.** `False` is the
  whole point of the field, and a truthiness test would report a correctly
  labelled preprint as missing one.
- **A Signal has no catch, so it has no dark slide.** The dark slide is
  where a post's caveat goes, and a roundup has five of them or none;
  forcing one item to go dark would say something about that item that is
  not true. `Format.catch` declares it and `proof.py` holds the render to
  whatever the format claims.

`formats.py` is its own module for the reason `llm_errors.py` is. Six places
need the answer — `render.py` refuses a record missing a field, `proof.py`
measures the word budget, `translate.py` knows what to translate, `site.py`
what to print, `telegram.py` what to show at the gate, and the template what
to lay out — and one of them cannot pay for it: `telegram.py` runs on
`publish.yml`'s poll under `requests` and `python-dotenv` alone and must
never import `render.py`. Do not put the table back there, and do not keep a second copy.

The Breakdown is the one format the pipeline does not draft. `docs` §4
splits the work by stakes — free-tier LLM for routine posts, this Claude
project where the explanation has to be excellent — and a Breakdown is
written by hand, then rendered, proofed, fact-checked and gated exactly like
any other post.

**A Signal is drafted, by `draft.py --signal`.** It is the same walk down
the queue as a Drop, five times, and the same code ownership of the credit
and the preprint flag applied per item rather than per post; one LLM call
writes all five claims. It moved off the hand-written side because a roundup
is not where the explanation lives — its per-item claim is a hook, not a
mechanism — and because the sourcing a person would do by hand is exactly
what `resolve_paper` already does. Four things make it different from
drafting five Drops:

- **The order the sources go into the prompt is the only thing tying a claim
  to its credit.** The model is told not to reorder, and a reply of the
  wrong length is refused outright rather than zipped against whatever lines
  up — silently pairing claim 3 with paper 4 puts the wrong authors' names
  under a result on a public slide.
- **It rejects what it cannot label, before the model is reached.** A Drop
  must draft the row it was handed and takes `peer_reviewed` from the reply
  where Crossref is silent; a Signal picks five from a queue of a thousand,
  so it can afford to want every item settled by Crossref or by a preprint
  host. The row stays queued — an unresolvable paper is still a fine Drop
  tomorrow — and the walk goes on rather than spending the LLM call and
  failing after it.
- **`covered_papers()` reads a Signal's items, not just its top level.** A
  roundup keeps `doi`, `attribution` and `source_url` per item and none on
  the post, so without that the five stories it covered were invisible to
  the duplicate guard and the next Signal would have picked them straight
  back out of the queue.
- **One budget, two reasons to walk on.** `check_budget` gives up after
  `MAX_DUPLICATE_SKIPS` rejections per item wanted, so a Drop still gives up
  after five and a Signal gets five times the rope for five times the work.

`draft.py`'s own `DRAFTED` names only what a *draft* needs beyond what
`render.py` will refuse to render — `post_type`, `domain`, `caption`.
Everything else it checks comes from `formats.required()`. It used to list a
Drop's body fields, which made it a fourth copy of the `formats.py` table
and the reason a Signal could not come out of this file at all.

`published_at` is not part of the contract and `draft.py` never emits it. It
is added by hand, as `YYYY-MM-DD`, when the post actually goes live on
Instagram, and it is the only thing that lets a post onto the public archive.
`render.py` ignores it. See **Web archive** below.

`metrics` is not part of the contract either. `telegram.py` writes it after
the post is live — `asked_at` when it asks for the numbers, then `saves`,
`shares`, `profile_visits` and `recorded_at` when you reply. `render.py` and
`site.py` both ignore it, so nothing it holds reaches a slide or a page. See
**Measuring** below.

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
- **A translation records the English it came from.** `translate.py` stamps
  the `es` block with a hash of the fields it translated, under `_en` — not a
  field any page renders, so `site.py` and `telegram.py` never show it. A post
  whose English is corrected at the gate is then re-translated by an ordinary
  `python src/translate.py`, rather than skipped as already translated while
  its Spanish goes on saying the old thing. A block written before the stamp
  existed carries none, and counts as unknown rather than stale: it is skipped
  as it always was, so nothing already reviewed is silently rewritten.

Machine-written Spanish on a permalink is the same credibility risk as an
unlabelled preprint, so it goes through Layer 5 like everything else: run
`python src/translate.py` and read what it prints **before** adding
`published_at`. `python src/translate.py --check` answers "is any of this
stale?" without an LLM call, and is what `check.yml` runs on every push.

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

## The drafting run

`daily.yml` on Monday, Wednesday and Friday — the three Drops `docs` §1
fixes the cadence at — drafts the top-scoring queued row, translates it and
commits the JSON, then calls `review.yml`, which fact-checks, renders, proofs
and sends to Telegram. It asks for four firings a day and drafts on one: the
cron is delivered hours late and unpredictably so (above), so the four are
one request repeated, and the `gate` job stands in front of the draft to
answer "has today already been drafted?" off the post's filename. A bare
`workflow_dispatch` is held to that too — on 2026-09-21 a hand dispatch sent
one minute after a six-hours-late cron had started produced a second
unwanted draft, because `concurrency` queues a run rather than dropping it.
The override is the `force` input, explicit for the same reason `--row` is:
naming a candidate by hand is an override, and a bare dispatch names nothing.

It ran daily until 2026-09-19 against a three-a-week pillar, and the four
surplus drafts a week each spent a draft call, a translate call, a
`fact-check` run on the Claude quota and a message in the chat, while the
buffer of undated drafts grew with nothing deciding how deep it should get.
`publish.yml` polls for the reply on a 15-minute cron that the free tier
actually delivers about every two hours. Between them sits a person, doing
what only a person can:

```
daily.yml ─ draft · translate · commit ──┐
recheck.yml ─ re-run the checks ─────────┤─→ review.yml ─ fact-check · render
fix.yml ─ apply the report · commit ─────┘                · proof · send
                                                                   │
                                                                   ↓
                                                               Telegram
                                                                   │
                          you read the reports, post the carousel  │
                          to Instagram, tap the button             │
                                                                   ↓
publish.yml ─ published_at · commit · dispatch site.yml ─→ the archive
```

`review.yml` is a `workflow_call` reusable workflow rather than steps inside
`daily.yml`, because two callers need it: the drafting run, and `recheck.yml`
when a review breaks rather than finds something. The gate that withholds the
button therefore lives in one place — a second copy is a second place to
forget to hold a post. It never drafts, never commits and never dates a post.
The caller commits first, which is what lets `review.yml` read the post in its
own checkout, and what lets `recheck.yml` find it again days later.

`recheck.yml` exists because re-running `daily.yml` is not the way back from a
held post: `draft.py` with no argument takes the *next* queued row, so a
re-run would skip the held post and spend tomorrow's story. Dispatched with a
blank `post` input it re-reviews the one awaiting approval.

Which post that is used to mean the newest dated file in `posts/` without
`published_at`, and the cadence decision made that answer wrong: at 3×/week,
drafted ahead and buffered from the evergreen queue, several undated posts are
the normal state rather than the broken one, and the newest of them is a
buffered draft rather than the post a person is looking at. So the question is
no longer "which draft is newest" but "which post is the person looking at",
and the chat answers it — `review.yml` uploads a `reports-<stem>` artifact for
every post it sends, so the newest surviving one names the post the gate last
spoke about, which is the post whose message carries the buttons. It needs
`actions: read` to ask; without a token it falls back to the old pick, which
is right only while there is one undated draft. The date-prefix filter in that
fallback is load-bearing rather than tidy: the `posts/era*.json` fixtures have
neither a prefix nor a `published_at`, and sort after every real draft, so
unfiltered one of them would be picked every time. That picking lives in
`.github/actions/resolve-post`, because `fix.yml` has to answer "which post is
held" identically or the two ways back repair different posts.

`fix.yml` is the other way back, and the two divide by *why* a post is held.
`recheck.yml` runs the same review again, which is the answer when the check
broke. `fix.yml` is the answer when the check was right: it fetches the
`reports-<stem>` artifact the holding run uploaded — the report the person
actually read, not a fresh one — applies it, re-translates, commits, and calls
`review.yml`. It is dispatched by tap and never scheduled, because some BLOCKs
are the checker being wrong rather than the post, and a Claude run spent on
every one of those burns the quota the checking itself needs. It never dates a
post: the corrected slides come back to the chat for approval exactly like the
first draft. Three limits hold it to repairing rather than rewriting:

- **It applies, it does not compose.** Where the report suggests replacement
  wording it uses that; where it does not, the unsupported claim comes out and
  the sentence runs shorter. The failure being repaired is a model writing a
  caveat the paper does not state, and a repair free to write a new one is not
  a repair. A finding that cannot be fixed by editing — the wrong paper, a
  post about something the source does not say — changes nothing and says why,
  because a post that needs re-drafting is not a post to patch.
- **A guard step on the diff, not the prompt, is what enforces that.** After
  the applier runs, `git diff --name-only` must name exactly the one post and
  the JSON must still have no `published_at`, or the run fails having
  committed nothing. The `settings` block is the contract; the diff is the
  proof.
- **It never grades itself.** The fact-check that decides whether the post is
  now true is the one `review.yml` runs afterwards, in a session that never
  saw the applier.

`src/telegram.py` is both halves — `send` and `confirm` — because both are
the same boundary, and its docstring holds the API-level reasoning. The
constraints that shape it:

- **The slides go as documents, not photos.** `sendPhoto` re-encodes to JPEG
  and downscales past 1280px. The slides are flat colour fields behind a 10px
  border, which is what JPEG bands worst, and they are about to be recompressed
  again by Instagram. Never switch the media group to `photo` to get inline
  previews — Telegram previews a PNG document anyway.
- **How many slides it sends is discovered, not counted.** `rendered_slides()`
  globs `slide-*.png` and orders by the number, because how many slides a post
  has is the template's business here exactly as it is in `render.py`. A fixed
  `slide-1..5` list sent five of a Breakdown's eight and printed "sent 5
  slides", which puts a person one tap from approving a carousel they saw half
  of. A hole in the numbering sends nothing: that is a render that stopped
  partway. `sendMediaGroup` takes 2–10 items, so a format longer than ten goes
  in evened-out groups rather than 10 + a remainder Telegram would reject.
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
- **`publish.yml` installs `requests` alone,** not `requirements.txt` — it is
  the most frequently run workflow here, and `telegram.py` deliberately does
  not import `render.py`, which would drag in Playwright.

### Both reviews gate the button

`telegram.py send --review FILE` carries each report into the message, and a
report containing `BLOCK` or `UNVERIFIED` withholds the approval button. That
is the gate: the ordinary tap that publishes is not offered on a held post.

What a hold cannot do is stop the carousel. Instagram is posted by hand,
outside all of this, so withholding every button protects nothing about the
account — it withholds only the *record*, and leaves a person who has already
posted with nowhere to say so except a hand edit to the JSON, which leaves no
trace that anything was overridden at all. So a held post carries three
buttons in place of the green one: **Apply the fixes**, **Re-run the checks**,
and **Posted anyway — record it**. The last dates the post as the green one
would; what
differs is that it carries `held:` rather than `pub:` in its `callback_data`,
so `confirm` knows it was an override and says so in the run log and in its
reply in the chat. A visible override is worth more than a gate that is only
technically unbroken — and the reports stay in the chat above it either way.

**Apply the fixes** is offered only when the *fact-check* is what held the
post. `fix.yml` applies a fact-check report and has nothing to say about a
layout `proof.py` measured and rejected, so offering it on a proof hold would
send a person to a workflow that reads the report, finds nothing it can act
on, and changes nothing.

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

**The gate reads a verdict line, not the prose.** Both checkers state their
finding on the report's first line — `PROOF · PASS`, `FACT-CHECK · PASS` — and
`BLOCK` there is what withholds the button. The first real fact-check to reach
this gate closed with "Safe to render — 0 BLOCK, 0 required FIX" and was held
by its own summary of having found nothing; a clean post held every day is
worse than no gate, because it teaches a person to tap the override without
reading.

A report with no verdict line still falls back to `GATE_RE`, which matches
`BLOCK` and `UNVERIFIED` case-sensitively on word boundaries. That is what
holds the stand-in review.yml writes when a configured fact-check produces
nothing, and what leaves the button alone for the "not configured" one, which
contains neither word.

Of those three buttons, only one is a real button. **Apply the fixes** and
**Re-run the checks** are **links** to `fix.yml` and `recheck.yml`, so the way
back from either kind of hold is one tap from the chat it arrived in. They are
links, and not buttons that do the work, because
`getUpdates` has no offset: a callback tap would replay on every poll for 24
hours and re-dispatch the work every quarter of an hour — burning the Claude
quota whose exhaustion is the likeliest reason the post is held at all.
`confirm` survives that replay only because dating a post twice is a no-op,
and neither a re-check nor a repair has such a marker. `workflow_url()` builds
both from `GITHUB_SERVER_URL` and `GITHUB_REPOSITORY` rather than from
constants, so a local `send` offers neither — whoever ran it by hand is
already at a machine that
can re-run the checks.

A third link, **Record it now**, sits under every publish button — the green
one and the override alike — and points at `publish.yml`'s
`workflow_dispatch`. It exists because a publish tap cannot be answered when
it is made: `confirm` runs on the cron, so by the time it sees the tap the
callback id is long past the seconds Telegram allows a bot to answer in, and
the message edit that *is* the acknowledgement is a couple of hours away.
Nothing visibly happens in between, which reads exactly like a bot that has
stopped working rather than one that is asleep.

So the fix is in two halves, and the copy is the larger one. `waiting_note()`
says in the message, before the tap, that nothing will appear to happen, how
long that lasts, and what the end of it looks like — a person who knows the
silence is normal does not need it shortened. The link is for when they want
it shortened anyway: two taps runs the poll, and the tap lands in under a
minute. It is safe to tap early, twice, or with nothing tapped at all, for the
same reason every other poll is — `confirm` is idempotent and a tap replays
for 24 hours.

Nothing gates a **local** `send` with no `--review` flags — the message says
plainly that nothing checked the post, but the button still appears, because
a person sending by hand is already in the loop. A local send offers no
**Record it now** either, for `workflow_url()`'s reason above, and the
waiting note drops its last sentence rather than pointing at a link that is
not there.

## Measuring

Layer 7. `docs` §9 makes saves the primary measure and shares the second,
`profile_visits` is the funnel one, and likes are explicitly not a metric.
§8 sets the decision it exists for: after thirty posts, cut the weakest
format and double the winner.

Instagram's numbers sit behind the Professional-account API that §4 rules out
on cost, so they are read by eye. The only design question is where a person
types three numbers with the least ceremony, and the answer is the chat the
gate already lives in.

`confirm` therefore does two jobs on the same poll: it stamps
the taps, and three days after a post went live it asks that post's numbers
and writes the reply into the post JSON. Four things hold it together:

- **The ask writes the block, not the answer.** `metrics: {asked_at}` is
  written when the question goes out, because that block is also what stops
  the question being asked again on the next poll. An unanswered ask is
  a block with no numbers in it, which `learn.py` reports as unanswered
  rather than as a zero — those are very different facts.
- **The answer is a reply, not a button.** Three integers do not fit in
  `callback_data` and no keyboard can carry an arbitrary number, so `confirm`
  asks Telegram for `message` updates as well as taps and reads the stem back
  out of `reply_to_message`. Nothing new is stored to link the two — which
  makes the reply *gesture* load-bearing. Three numbers typed as an ordinary
  message name no post, and `record_metrics` drops them: with several asks
  outstanding at once, which is the normal state, nothing can say which one
  they answer, and guessing would put invented numbers into the §8 decision.
  Asking in words did not secure it. The message has said "Reply to **this**
  message" in bold since it was written, and on 2026-09-21 nine answers
  arrived unreplied over a single day and every one was lost. So the ask
  carries `METRICS_FORCE_REPLY` — Telegram's `ForceReply`, which has the
  client open the reply box already pointed at the question, so the link is
  made by the keyboard rather than by remembering. The sentence stays, for
  whoever dismisses the keyboard.
- **It survives the missing offset like `published_at` does.** Recording a
  number is a set, not an increment, so a reply replayed for 24 hours writes
  what is already there. Two replies that disagree are a correction, and
  `getUpdates` returns them oldest first, so the later one lands last.
- **A numbers-only poll does not rebuild the archive.** `site.py` ignores
  `metrics`, so a rebuild would produce identical HTML. `confirm` reports
  `published=true|false` on `GITHUB_OUTPUT` and `publish.yml` dispatches
  `site.yml` on that. Do not go back to reading it off the diff: writing a
  metrics block next to `published_at` puts a comma on that line, so the diff
  claims a publish on a poll that published nothing.

`python src/learn.py` is the report — medians by `post_type`, `colorway`,
`domain` and weekday, then every measured post ranked by saves. It holds back
a group under three posts rather than ranking noise, and says outright that
§8 puts the format decision at thirty. It computes no rate: saves per
impression would be the honest measure and Instagram does not give
impressions away, so a ratio built from these three numbers would look
rigorous and mean nothing.

## When something breaks

Two pieces, because the failures divide in two.

**`check.yml` runs on every push** and exercises the half of the pipeline
that needs no secret, no network and no LLM call: every module in `src/` is
loaded by path, `posts/era.json` is rendered and proofed, the whole archive is
built, and `translate.py --check` confirms no post's Spanish is older than its
English. A second job installs *only* the two packages `publish.yml` installs
and loads `telegram.py` under them — that list is maintained by hand against
`telegram.py`'s imports, and the day it fell behind, `confirm` died at module
load on every poll for a day.

That job is deliberately not a test suite: it asks whether the pipeline still
runs end to end, and it catches the class of break that used to surface at
06:17 — a missing dependency, an import cycle, a template that stops
rendering, Spanish left behind by a correction.

**The test suite is a third job**, `tests`, over `tests/` with pytest. It asks
a different question — does this function still do what the post-mortem says
it must — which is why it is a job of its own rather than more steps in
`smoke`: a red there names a stage, a red here names a behaviour. Run it with
`python -m pytest`; `requirements-dev.txt` pulls in `requirements.txt` and
adds pytest, and nothing in it touches the network, an LLM or a browser.

Every test in it is a case this repository has already got wrong once. That
is the entry criterion, and it is what keeps the suite from growing into
something nobody reads:

- `resolve_paper` walking into a paper's own reference list and crediting
  Wegst et al. (2014) on a 2026 story (2026-09-18).
- A fact-check held by its own closing summary of having found nothing.
- Spanish reported as up to date on fifteen posts nothing could check.
- `--evergreen` re-drafting the tides post, still #1 in the queue.
- A metrics reply silently dropped because the mark moved behind an emoji.
- Five of a Breakdown's eight slides sent to the gate, reported as five.
- Every `era*.json` fixture reported as clashing with the newest real draft,
  because a path outside `post_order()` is read as arriving at its end.
- Nine metrics answers typed into the chat instead of replied with, dropped
  in silence, while `learn.py` reported the asks as simply unanswered.

What none of the three jobs can catch, so nobody mistakes green for safe:
anything that needs a real run — Telegram's message cap, a checkout resolving
to the wrong SHA, a provider's 429. Green is not safe, it is only "nothing
obvious".

Note that commits pushed by the workflows themselves use `GITHUB_TOKEN`, which
by design does not trigger other workflows, so a bot-committed draft is not
checked. A hand correction at the gate is pushed by a person, and is.

**A failed run says so in Telegram.** `.github/actions/notify-failure` is a
composite action called from an `if: failure()` step at the end of every
scheduled workflow, and it posts the run URL to the same chat the gate uses.
It lives in one file for the reason `review.yml` does. Two details:

- **It speaks on every failed run, `publish.yml`'s poll included.** It used
  to take an `hourly: 'true'` from `publish.yml`, which silenced any run
  starting after minute 15 — the throttle that kept a quarter-hourly cron
  from sending 96 identical messages a day and teaching a person to mute the
  bot. That check was a proxy for "the first poll of the hour", and it was
  only ever equivalent while the polls landed on :00/:15/:30/:45. At the
  cadence the free tier actually delivers (above) the runs land at whatever
  minute they like, and six of the eight measured would have been silenced —
  a one-off failure as readily as a persistent one. An action that exists
  because failures were invisible cannot drop three alerts in four, and the
  spam it insured against is now capped by the platform at about eight
  messages a day. A stateless step cannot tell a repeat from a first
  sighting, so the throttle is gone rather than rebuilt.
- **Missing credentials are a no-op, not a second failure.** The point is to
  make a break visible, never to add one on top of it.

## Watching the pipeline

`notify-failure` speaks for a run that started and broke. `watch.yml` is what
speaks for one that never started, and it can only do that by being a
different run: `src/watch.py`, once a day, asking what the pipeline should
have left behind and reporting what is not there. It sends one message or
none.

```bash
python src/watch.py                  # print the report
python src/watch.py --send           # ...and send it if it is not a PASS
python src/watch.py --skip-feeds     # skip the slow network sweep
```

Nine checks, each answerable from a file, a sheet cell or a Telegram update —
so none of it needs a model and none of it spends a quota:

| check | the question |
|---|---|
| `cadence` | the last Drop day that **ended** has a post dated it |
| `gate` | every tap in Telegram's 24h window reached `published_at` |
| `metrics` | every answered ask was written down, no answer arrived unreplied, and old asks were answered |
| `colour` | no two neighbouring posts share a field |
| `buffer` | drafts are not silently piling up at the gate |
| `feeds` | every feed still returns entries, and still publishes them |
| `queue` | rows are still arriving, and candidates are still scored |
| `structure` | `check.yml`, whose result the workflow hands over |
| `fact-check` | it is configured at all |

Six things hold it together, and every one of them is a rule about not crying
wolf — a watcher nobody reads is worse than none:

- **It only asks about obligations that have already come due.** A daily cron
  arrives 3–6 hours late, so `last_drop_day()` walks back from *yesterday*,
  never from today. A day that has ended owes its post unconditionally; today
  might just be running behind. This is why `watch.yml` asks once rather than
  copying `daily.yml`'s four firings: that shape exists to land near an hour,
  and this has no hour to land near.
- **A finding nobody can act on is a note, not a finding.** Notes print but
  do not move the verdict, and only a non-`PASS` verdict sends. A colour run
  that is already published is history — there is nothing to re-render and no
  tap to withhold — so it stays visible in a hand run and silent in the chat.
  The same reasoning as a clean fact-check that must not hold a post.
- **Findings exit 0.** The message *is* the report. A non-zero exit would
  make `notify-failure` send a second message about the same thing. Only an
  unexpected failure exits non-zero, and that genuinely is a broken run.
- **Every check degrades rather than dying.** `open_sheet()` exits with
  instructions when the credentials are missing; `watch.py` catches that and
  reports the queue as unchecked. A watcher that dies on one unconfigured
  check reports nothing about the eight that are fine.
- **It reads `getUpdates` without an offset, like `confirm` does.** That
  leaves the cursor alone, so reading the same 24-hour window from a second
  process cannot take a tap away from the poll meant to act on it.
- **`check.yml` runs as a called workflow, not as copied steps.** It gained
  `workflow_call` for this. The point is the hole `check.yml` documents in
  itself: bot commits use `GITHUB_TOKEN` and do not trigger its `push`, so
  the three drafts a week the bot writes were never exercised. Its result is
  passed to `watch.py` with `--structure` so a red check is a line in the
  message rather than an ✗ on a run nobody is watching.

**`watch.yml` installs `requirements.txt` but not the browsers.** `watch.py`
imports `render.py` for `post_order()` and `vary()`, and `render.py` imports
Playwright at module level — but the pip package imports fine without
`playwright install`, and nothing here ever opens a page.

Three things it cannot do, which matter as much as what it can:

- **It cannot prove it ran.** It is on the same scheduler that sheds, so its
  silence means "nothing to report" *or* "I did not run", and nothing
  distinguishes them. Making its absence visible costs a message a week; that
  trade is open, not made. Do not "fix" it by tightening the cron.
- **Telegram does not timestamp a tap.** `callback_query` carries no date, so
  a tap made shortly before a run is indistinguishable from one the poll
  lost. That is why an unrecorded tap is a FIX that says the poll may still
  be pending — a genuinely lost tap reports every day until it is fixed, and
  that repetition is the signal.
- **It does not measure how late a cron was.** The Actions API would give
  that and it would change nothing, since GitHub cannot be asked for less
  delay. So `watch.yml` asks for no `actions:` permission at all.

## Publishing

Meta Business Suite Planner, manually, is the current path. It is free,
first-party, supports carousels, and has no post cap.

The Instagram Graph API is a later option: free but gated by app review,
requires a Professional account linked to a Facebook Page, uses a two-step
container + publish call, has **no native scheduling endpoint**, and caps at
50 API-published posts per rolling 24 hours. Do not start building against it
without an explicit decision.

## The status-report pillar

A second content stream beside the carousels: single 1080x1350 slides of
relatable-dev humour under a `STATUS REPORT #NN` eyebrow, one a day.
`series.yml` sends the next one to the same Telegram chat with its caption and
one button; `publish.yml`'s existing poll takes the tap back. Layer 5 applies
here exactly as it does to a Drop.

Its strategy, numbering contract, design tokens and what is built lives in
`docs/gummietech_status_reports.md` — read it when the task touches what gets
posted rather than how the sending runs. `python src/series.py` prints the
queue: what is next, what is missing an image, how many days of runway are
left, and whether the numbering has a hole or two neighbours share a module.

**It is not a `post_type`, and adding one would be the mistake.**
`formats.RECORD` requires `attribution`, `source_url` and `peer_reviewed` on
every record and `render.load_post()` refuses one without them — because a
post that cannot name its source must not ship. A status report has no source
to name. It also uses a different, locked design system (warm cream
`#F3EEE6`, Instrument Serif / Manrope / JetBrains Mono) that has nothing to do
with `templates/tokens.css`. So it gets `src/series.py`, a small stdlib-only
manifest module, and nothing in `src/` renders it.

**The slides are exported by hand.** They are designed on a Claude Design
canvas and exported to `series/images/` — that export is a click in a browser
and no workflow can do it. `.gitignore` blanket-ignores `*.png`, so
`!series/images/*.png` is what lets them be committed at all; delete that line
and `series.yml` silently finds no image and sends nothing.

Four things that are deliberate:

- **A third callback prefix, `ser:`.** It dates a record exactly as `pub:`
  does, so it looks like duplication. It is not: `confirm` reports
  `published=true` on `GITHUB_OUTPUT` and `publish.yml` dispatches `site.yml`
  on it, and `site.py` reads `posts/` and nothing else — so a report tap
  answered as `pub:` would rebuild the archive into byte-identical HTML every
  day it went out. The same shape as the metrics-comma bug: a write next to
  `published_at` claiming a publish that did not happen.
- **One poller, not two.** `getUpdates` is called without an offset, so every
  tap replays for 24 hours; a second polling workflow would see and answer the
  same taps. `confirm` handles both pillars, and `locate()` is the one lookup
  that finds a stem in either collection.
- **`sent_at` is not `published_at`.** Sending writes nothing else, so
  `series.yml`'s gate has no filename to test the way `daily.yml` tests
  `posts/<today>-*.json`. `sent_at` is that marker — and "the bot showed it to
  me" and "I put it on Instagram" are different facts, hours apart.
- **A report with no image yet is not a failed run.** The queue runs ahead of
  the export, so `send-series` says what is missing in the chat and exits 0.
  Failing would fire `notify-failure` every day until someone sat down at a
  computer, which teaches a person to ignore the bot. It does not skip ahead
  to the next report that *is* ready: the numbering is public, and a gap reads
  as posts gone missing.

`python src/learn.py --series` is the Layer 7 half, grouped by `module` and
`eyebrow` rather than `post_type`/`colorway`/`domain` — what varies in this
pillar is the layout the slide is built from, and "which module earns another
ten" is §8's format decision one pillar down.

## When updating strategy

`docs/gummietech_content_system.md` and this file both describe the project
and can drift. If a change here affects strategy — or vice versa — say so
rather than silently updating one.
