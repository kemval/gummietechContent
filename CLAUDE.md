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
| LLM scoring | Gemini 3.5 Flash Lite free tier, fixed in `ingest.yml`; drafting and translation on `LLM_PROVIDER` (Groq); OpenRouter `:free` models as the last fallback |
| Rendering | Playwright → PNG |
| Templating | Jinja2 |
| Config | YAML feed lists, `.env` for secrets |

## Layout

```
.claude/agents/      fact-check · slide-proof · feed-scout · evergreen-scout
                     · voice-review · metrics-analyst (all read-only: they
                     report or propose, a person decides — see below)
.github/actions/     notify-failure (one definition of "this run broke",
                     called by every scheduled workflow) · resolve-post
                     (one definition of "the post that is waiting") ·
                     install-render-tools (Chromium + ffmpeg, bounded and
                     retried against a crawling Ubuntu mirror) ·
                     push-to-master (the one way a job pushes: rebase,
                     retry a race, fail on a conflict) · heartbeat (the
                     ping an outside watcher expects — see below)
.github/workflows/   check.yml (on push: the offline half, no secrets) ·
                     ingest.yml (feeds+scoring, 2h) · daily.yml (draft →
                     commit, Mon/Wed/Fri, Wed as `--run`; the Signal Sat) ·
                     weekly.yml (Claude writes Tue's term, Thu's
                     Breakdown → commit) ·
                     review.yml (fact-check · render
                     · proof · send — called, never scheduled) · recheck.yml (run
                     review.yml again on a held post) · fix.yml (apply the
                     fact-check to a held post, then review.yml again) ·
                     hook.yml (put another of a draft's hooks on the cover,
                     then review.yml again) · redraft.yml (reject the
                     waiting draft, draft the next story, review.yml) ·
                     publish.yml (the publish tap, 15m) · site.yml (archive) ·
                     watch.yml (daily: is any of this still running?) ·
                     series.yml (the status-report pillar, daily) ·
                     reel.yml (a published Drop as a reel — on request)
src/
  formats.py         what each carousel format is made of — the one table
  verify_feeds.py    checks every feed URL is live
  ingest.py          feeds → Google Sheets
  llm.py             picks the scoring backend from LLM_PROVIDER
  gemini.py          Gemini request + free-tier retry policy
  groq_llm.py        Groq request, same interface as gemini.py
  openrouter_llm.py  OpenRouter `:free` request, the last fallback
  score.py           LLM scoring, batched
  papers.py          page → DOI → Crossref → the paper a story covers,
                     and the paper-first text a post is drafted from
  draft.py           winning item → papers.py → JSON;
                     --signal walks five rows for the weekly roundup
  render.py          JSON + template → PNGs
  reel.py            a published Drop → silent 9:16 MP4, frame by frame
  build_kit.py       The Build's stills (cover, cards, lower third) from
                     docs/build_episodes.md — the reel itself stays manual
  proof.py           measures the rendered layout — frame, contrast, flag
  wording.py         the voice rules code can check: dating words, and
                     "you" or an unattributed figure in a maker's release
  hook.py            swaps a draft's cover line for one of its alternates
  weekly.py          Tuesday's term and Thursday's Breakdown: is it owed,
                     what is it built from, and the check, file name and
                     credit around Claude's draft
  site.py            published posts → static web archive, with each
                     post's slide 1 as its link-preview image
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
posts/               drafted post JSON; posts/rejected/ holds drafts
                     turned down at the gate — dedup memory, nothing else
templates/
  tokens.css         the locked palette and type stack — included by both
  slides.css         the slide design (v2), shared by every format + reel
  slide_parts.html   macros every format shares: corners, cover, catch, follow
  slides_layout.js   the layout pass: measures and fits, never writes text
  drop.html          production slide template — 1080x1350
  drop_slides.html   the Drop's five slides, shared with reel.html
  breakdown.html     8–10 slides; signal.html — the weekly roundup
  run.html           a Drop + the code slide; term.html — the glossary;
                     sheet.html — the cheat sheet
  build.html         The Build's 9:16 kit, inside the reel and 4:5 grid crops
  reel.html          the same slides swiped through at 1080x1920
  site_base.html     web archive shell; index.html and post.html extend it
output/              rendered PNGs (gitignored)
site/                built web archive (gitignored)
docs/                strategy reference; docs/decisions/ holds the
                     reasoning behind each rule in this file
```

## How this file is organised

Each section below states the rules in a line or two. The reasoning, the
measurements and the post-mortems behind them live in `docs/decisions/`,
one note per area. **Read the linked note before changing code in that
area** — the rules here are the conclusions, and the notes are what stops
a "cleanup" from undoing a fix that was paid for.

## Non-obvious constraints — read before writing code

**Fetch feeds with a browser User-Agent.** Reuse the headers in
`src/verify_feeds.py` everywhere a feed is fetched; a Cloudflare block page
reaches feedparser as a "not well-formed" XML error. → `docs/decisions/feeds.md`

**Feed URLs move constantly.** Never hardcode a URL from memory. Run
`python src/verify_feeds.py -v` after any change to `feeds/`; `feed-scout`
proposes fixes, a person verifies and commits. **And a feed can be live and
finished at the same time** — both the checker and `watch.py` measure the
newest entry's age against `STALE_AFTER_DAYS` (60). A newsroom's `announces`
prefixes are checked the same way (`announces_drift`). A feed with a
`kind` is not RSS (`hf_daily_papers`, Hugging Face's JSON API): every reader
goes through `verify_feeds.parse_feed()`, never feedparser directly.
→ `docs/decisions/feeds.md`

**Batch LLM scoring 15–20 items per request**, with a Python keyword
pre-filter first. Gemini's free tier has a per-minute and a daily cap, per
project; back off on 429, fail fast on a daily-cap error. **Scoring runs on
Gemini 3.5 Flash Lite (500 requests a day), pinned in `ingest.yml`; never on
Gemini 3.5 Flash, whose free tier is 20 a day** against 40–80 needed. Read
the caps in AI Studio, not from memory or third-party pages.
→ `docs/decisions/llm-providers.md`

**Swapping to Groq** is `LLM_PROVIDER=groq` plus `GROQ_API_KEY`;
`groq_llm.py` mirrors `gemini.py`, and its daily-vs-per-minute 429 parse is
unverified. **The providers fail over down `llm.FALLBACK_ORDER`** — on 5xx
exhaustion only, sticky for the process, carried by `llm_errors.Overloaded`;
a fallback with no key is skipped. A bad key, retired model or spent daily
cap still stops the run. The third link is OpenRouter (`openrouter_llm.py`):
`:free` model ids only, refused otherwise; 50 requests a day, so always
last; its 503 means the privacy setting, not overload. Cerebras needs a
card; GitHub Models was retired 2026-07-30.
→ `docs/decisions/llm-providers.md`

**GitHub Actions cron is a request, not a promise.** A `*/15` cron is shed
to about eight runs a day; a daily cron always runs but 3–6 hours late.
Nothing here may depend on punctual execution. A workflow that must land
near an hour asks several times and gates the extra firings to no-ops
(`daily.yml`'s shape); never tighten the interval instead.
→ `docs/decisions/scheduler.md`

**The runner is pinned to `ubuntu-24.04`, and `ubuntu-latest` is the bug.**
Every job carries the pin with a one-line reason. Unpin deliberately: a
green `check.yml` on `ubuntu-26.04` first, then every job.
→ `docs/decisions/runner-pin.md`

**The queue is deduplicated by URL, and a story is not a URL.** `draft.py`
resolves each candidate's DOI before the LLM call and skips a paper already
in `posts/` (`MAX_DUPLICATE_SKIPS` caps the walk). **Do not rebuild
title-based deduplication** — it was measured and removed on 2026-09-21. A
launch has no DOI, so its key is its maker's page: newsroom feeds declare
`announces` prefixes, and coverage that links an announcement already posted
is a duplicate.
→ `docs/decisions/dedup.md`

**Drafting takes only fresh news.** `pick_row()` skips a queued row whose
story is older than `ingest.MAX_STORY_AGE_DAYS` (10), by `published`, else
`fetched_at`; undated is too old. The rows stay queued, and `--row` is the
override. `watch.py` counts the queue the same way. The queue ranks by score
alone and held a month of backlog, so a launch went out 34 days late.
→ `docs/decisions/voice-and-selection.md`

**The sheet grows forever, and that is fine — do not build a purge.**
`rejected` rows are the deduplication memory; deleting them re-ingests and
re-scores. If a purge is ever needed, age is the only safe rule and undated
rows are never safe. **Never sort it either:** `score.py` and `draft.py`
write back by row number, and `ingest.check_unmoved()` stops a run whose rows
moved under it. → `docs/decisions/sheet-growth.md`

**The account is tech-first, and the score is not where that lives.**
`score.py` names each item's `beat`; `draft.pick_row()` prefers
`PRIORITY_BEATS`. Do not move the preference into the score.
→ `docs/decisions/tech-first.md`

**Launches are news, and the voice is a doc.** `score.py` also asks for
`relevance` (would someone who uses technology want this today?) — a lift,
not a fifth axis: at `LIFT_AT` (8) it becomes the score, below it the mean
of the four axes stands. Averaging it in was measured and gutted the queue.
Funding, personnel news, drama, customer stories and capability-free
marketing stay at 3 or below. How every post
sounds lives in `docs/voice.md`, pasted into `draft.py`'s prompts and named
in `weekly.py`'s brief. The prompt's fact rules outrank it. The three rules a
word list can check — no dating words, and in a maker's release no "you"
and no figure without "says" —
are `wording.py`'s: `draft.py` drops a cover line that breaks them, and
`proof.py` reports what remains as a FIX at the gate.
→ `docs/decisions/voice-and-selection.md`

**`draft.py` drafts from the paper, not the coverage.** DOI from the page
(meta tag, then journal-reference heading, then anywhere), Crossref for
authors and abstract, coverage demoted to context. Every step degrades to
coverage-only drafting with a warning. For the one paper a Drop is drafted
from, `papers.fetch_limits()` reads the body and quotes only the sentences
that state a limit (`LIMITS_CHARS`, for Groq's 8000-token minute) — abstracts
leave the catch out. → `docs/decisions/paper-first.md`

**Secrets** go in `.env` locally and GitHub Actions repo secrets in CI.
Never commit `.env`, `credentials.json`, or any key.

## Rendering

Slides render at **1080×1350** (4:5), one `.slide` div each inside
`templates/<post_type>.html` (fallback `drop.html` with a warning), each
screenshotted individually, and each also filmed as a seamless 8s MP4 of its
moving backdrop (Neat-style ribbons, our own shader, in the post's own
lead/support/cream since 2026-10-06 — never a fixed table; `--no-motion` skips). `render.py` discovers slides with
`querySelectorAll('.slide')` and refuses fewer than `MIN_SLIDES` (4).

Design tokens are locked — do not change them or propose alternatives. They
live in `templates/tokens.css`, shared by the slides and the archive; do not
copy them into a third place:

```css
--pink:  #EE6EC0;   /* field */
--olive: #B2BC5F;   /* field */
--cream: #F7EFE2;   /* neutral field, always slide 2 */
--ink:   #3B2C23;   /* outline + type, not black */
--blush: #F9A8D4;   /* field, sparing */
--sky:   #7FB2E5;   /* field */
--amber: #F2B441;   /* field */
```

**Every carousel format and the reel are on design v2** (`slides.css`, 2026-09-28), **with v3's grid layer** (2026-09-30: hairline rules, a same-hue backdrop, outline ghosts, keyword callouts — see the note): Hubot
Sans for display, Mona Sans for body, Monaspace Neon for labels (GitHub's OFL
type system, since 2026-09-30), no drawn frame — type sits 60px from the edge, and `.frame` survives as an invisible
box inset 34px that `proof.py` measures against. Content is always full
`--on-field`; only corner chrome (`.lbl`) is muted. **Every word is a record
field or fixed template copy**: `render.py` only *chooses* spans of the
record to box, set large or strike (`emphasis`, `cover_figure`,
`catch_diff`), and `typeset` ("1.81x" → "1.81×") is the only character it
changes. A cover figure never appears without the hook's own qualifier.
The web archive (`site_base.html`) is on v2 too — flat colour blocks, mono
labels, the same fonts at `font-display: swap`. The type stack lives in
`tokens.css` with the palette; do not restate it in a template.
→ `docs/decisions/rendering.md`

### Colorways

`COLORWAYS` in `src/render.py` is the single source of truth; address
colour by role (`--field`, `--on-field`, `--frame`, `--flag-bg`/`--flag-fg`),
never hardcode a hue in a template. A Drop renders
`lead · cream · support · dark · lead`:

| family | topics | lead | support |
|---|---|---|---|
| `signal` | AI, computing, software, robotics | pink | olive |
| `orbit` | space, astronomy, physics | sky | pink |
| `bloom` | biology, medicine, climate, ecology | olive | blush |
| `ember` | energy, materials, engineering, chemistry | blush | amber |

Invariants (`render.rhythm()` is them as code): `--ink` is the type on
light slides; slide 2 is cream; the catch is the second-to-last
slide and drops to `--ink`; first and last slides share a field; the middle
alternates support and lead; every lead/support hue clears 4.5:1 against
`--ink` (asserted in `tests/`); **no two consecutive posts share a field**
(`render.vary()`, deterministic, comparing colour pairs, not names). `render.py --colorway <name>` overrides at
the gate. → `docs/decisions/rendering.md`

### Drop reels

`src/reel.py`, on request only, for published Drops: no words of its own,
captured frame by frame through the Web Animations API, ffmpeg apt-installed,
slides kept inside `SAFE_TOP`/`SAFE_BOTTOM`, preprint flag checked on every
frame. Audio is never added. The selection box draws itself, the catch's
diff strikes its figure, and the cover swipes back in so the reel loops —
animated elements are real ones, never `::before`. The Build's cover and
cards come from `src/build_kit.py`; its reel is still a person's.
→ `docs/decisions/rendering.md`

### Proofing the render

`python src/proof.py <post>` measures the live DOM (shared `open_page()`)
and reports BLOCK / FIX / PASS: elements measured by shape, collisions by
line boxes, contrast bar 4.5:1 for content and 3.0 (FIX only) for chrome;
`check_colorway()` reports a repeated field as a FIX. The `slide-proof`
agent is the read-only visual check for what measurement cannot see.
→ `docs/decisions/rendering.md`

## Fact-checking a draft

Run the `fact-check` agent (`.claude/agents/fact-check.md`) before rendering.
It is read-only — never give it Edit or Write, never let it add
`published_at`. `fix.yml` applies its report in a separate session, guarded
by a diff check; a fresh `review.yml` re-checks the result. Watch for the
wrong author, a preprint behind a journal URL, and a `the_catch` the paper
does not state. A source that cannot be read is a hold, not a pass.
→ `docs/decisions/fact-check.md`

## Drafting output contract

`draft.py` must emit strict JSON, no prose, no code fences:

```json
{
  "post_type": "drop | run | breakdown | term | sheet | signal",
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

- `attribution`, `alt_text` and `domain` are required; `render.py` refuses a
  record missing them. When a DOI resolves, `attribution` comes from Crossref.
- `colorway` falls back to `signal` with a warning.
- `the_catch` may be `""` — the model's answer when the text it was given
  states no limitation, instead of inventing one. It renders a held slide,
  `proof.py` BLOCKs it, and the fact-check's replacement is what **Apply the
  fixes** writes in (`formats.UNSTATED`). A missing key is still refused.
- When `peer_reviewed` is false the template must show the
  "Preprint — not yet peer-reviewed" flag, enforced in code — **unless**
  `"announcement": true`: a maker's own launch with no study behind it,
  whose cover says "Announcement — not a peer-reviewed study" instead.
  `formats.preprint()` is the one rule every label reads. A page under a
  newsroom's `announces` prefix with no paper is an announcement by code
  (`draft.maker_announcement()`), so a Signal may carry it; elsewhere the
  model proposes it and `draft.validate()` drops it whenever a paper
  resolved or the host is a preprint server. Absent on every older post.
- Written by code, never the model: `hooks`, `beat`, `code_url`, `doi`, `es`
  (`translate.py`), `metrics` (`telegram.py`), and a run post's `post_type`
  (`draft.py --run`, only when a README was read). `published_at` is added only
  when the post goes live, and `draft.py` never emits it.
- The body fields above are the Drop's. `src/formats.py` is the one table of
  what each `post_type` carries (Breakdown, Signal with per-entry credit,
  a glossary `term` with a published `example_post`, a `sheet` of
  `"Term: line"` strings, a `run` with `try_it` from the repo's README);
  do not copy it anywhere, and `telegram.py` must never import `render.py`.
- A term (Tuesday) and a Breakdown (Thursday) are written by Claude in
  `weekly.yml`, and a sheet by hand — none by `draft.py`. `formats.by_hand()` is the
  one test of that, for the Drop-day gate, `watch.py` and redrafting;
  never compare `post_type` to `"breakdown"`. A Signal is drafted by
  `draft.py --signal` on Saturday, a run post by `--run` on Wednesday.
  Their credit is copied by `weekly.py` from the published post they build
  on (a term's `example_post`, a Breakdown's Drop), never written by the
  model.

→ `docs/decisions/post-record.md`

## Code style

- Complete working files, not fragments.
- Type hints on function signatures.
- Every network call wrapped with explicit timeout and error handling.
- Error messages say what to do next, not just what failed.
- Standard library where it suffices; no dependency for twenty lines of code.
- Comment the non-obvious constraints above wherever they appear in code,
  since they are invisible failure modes otherwise.

## Web archive

`src/site.py` builds `posts/*.json` into a static site deployed by `site.yml`
to <https://kemval.github.io/gummietechContent/> — the Instagram bio link.

- **`published_at` is the human gate.** `site.py` skips any post without it;
  never add a fallback that publishes undated posts.
- **It is not a blog.** Every page is a pure function of the draft JSON.
- **It wears the slides' moving backdrop** (`templates/backdrop.js`, one
  shader for slides, reel and archive), live, still under
  `prefers-reduced-motion`, flat without WebGL.
- Each post page uses its own rendered slide 1 as the link-preview image;
  a browser that will not launch degrades to text-only previews.
- A malformed post is skipped with a warning, never fails the build.
- **Spanish** is the post's `es` block from `src/translate.py`, stamped with
  a hash of its English (`_en`); partial Spanish is dropped whole; the
  toggle renders only when the page has Spanish. Read what `translate.py`
  prints before adding `published_at`. `translate.py --check` runs in CI.

→ `docs/decisions/web-archive.md`

## The drafting run

```
daily.yml ─ draft · translate · commit ──┐
weekly.yml ─ Claude writes · commit ─────┤
recheck.yml ─ re-run the checks ─────────┤─→ review.yml ─ fact-check · render
fix.yml ─ apply the report · commit ─────┘                · proof · send
                                                                   ↓
                          a person posts the carousel,          Telegram
                          then taps the button                     ↓
publish.yml ─ published_at · commit · dispatch site.yml ─→ the archive
```

- `daily.yml` drafts Mon/Wed/Fri (and the Signal on Saturday), firing four
  times and gated to one draft per day; `force` is the override. Wednesday
  passes `--run`, which falls back to a plain Drop when nothing links code.
- `weekly.yml` writes Tuesday's term and Thursday's Breakdown the same way
  (four firings, one post, `kind` and `force` on dispatch). Claude writes
  outside the repo from `weekly.py brief`; `weekly.py finish` refuses a bad
  draft, names the file and copies the credit; a fresh fact-check in
  `review.yml` grades it. A Breakdown explains a published Drop, tech
  first, whose paper no Breakdown covers yet — code picks it, not Claude.
- `review.yml` is the one reusable review; callers commit before calling it.
  `.github/actions/resolve-post` is the one answer to "which post is held".
- `hook.yml` swaps the cover line and re-runs the whole review.
- `redraft.yml` (**Another story**) moves the waiting draft to
  `posts/rejected/` with the reason given, drafts the next story, and
  reviews it. Moved, not deleted: `covered_papers()` reads it as dedup
  memory; every other reader globs `posts/*.json` and never sees it.
- `telegram.py` sends slides as documents (never photos), discovers how many
  slides there are, carries the post stem in `callback_data`, and calls
  `getUpdates` **without an offset** — `confirm` is idempotent; do not add
  offset tracking. Both readers go through `telegram.poll()`, honour only
  `TELEGRAM_CHAT_ID`'s updates (`ours()`), and warn when a poll hits
  `UPDATES_LIMIT` — unacknowledged, 100 is the cap on the whole 24 hours.
- `review.yml` checks the fact-check left `posts/`, `src/`, `templates/`
  as committed; a change is restored and the post held `UNVERIFIED`.
- `publish.yml` dispatches `site.yml` by name and installs only `requests`
  and `python-dotenv`.

### Both reviews gate the button

A report whose first-line verdict (`PROOF · …`, `FACT-CHECK · …`) says
`BLOCK` or `UNVERIFIED` withholds the green button; a report with no verdict
line falls back to `GATE_RE`. A held post offers **Apply the fixes** (only on
a fact-check hold), **Re-run the checks** (both links, never callbacks) and
**Posted anyway — record it** (`held:`, a visible override). **Record it
now** links to `publish.yml`'s dispatch. No `CLAUDE_CODE_OAUTH_TOKEN`, no
gate change; a configured check that fails writes `UNVERIFIED`.

→ `docs/decisions/drafting-run.md`

## Measuring

Three days after a post goes live `confirm` asks for saves, shares,
profile visits, accounts reached and follows (with `ForceReply`) and writes
the reply into `metrics`; the first three alone still count, and a field not
given is missing, not zero. The
ask writes `asked_at`; an answer must be a reply to the ask or it is
dropped; a numbers-only poll reports `published=false` so the archive is not
rebuilt. `python src/learn.py` is the report — no rates, groups under three
held back, §8's decision at thirty posts. → `docs/decisions/measuring.md`

## When something breaks

- `check.yml` on every push: the offline half end to end, a job that
  loads `telegram.py` under `publish.yml`'s two packages only, and
  actionlint (with shellcheck) over every workflow. Deliberate word
  splitting carries a `shellcheck disable` comment with its reason.
- **Merge a PR only on a green `check.yml`** — by habit, not by rule: branch
  protection would also block the bot's direct pushes to `master`. A PR with
  conflicts gets no CI run at all; an unrun check is not a pass.
- `tests/` (pytest, `python -m pytest`): **every test is a case this repo
  already got wrong once** — that is the entry criterion.
- `.github/actions/notify-failure` posts every failed run's URL to Telegram,
  unthrottled; missing credentials are a no-op.
- `.github/actions/install-render-tools` is the only place Chromium and
  ffmpeg are installed: five minutes an attempt, one retry, and every
  caller's `timeout-minutes` leaves room for both.
- Green is not safe, only "nothing obvious". Bot commits do not trigger
  `check.yml`.

→ `docs/decisions/breakage.md`

## Watching the pipeline

`src/watch.py`, via `watch.yml` once a day, reports what should have
happened and did not (cadence, glossary, breakdown, subject, gate, metrics, colour,
buffer, feeds, queue, lift, structure, fact-check). It only asks about obligations
already due, keeps unactionable findings as notes, exits 0 on findings,
degrades per check, and reads `getUpdates` without an offset. It cannot
prove it ran — so `watch.yml` and `ingest.yml` end on `heartbeat`, a ping to
healthchecks.io (free Hobbyist plan) that alerts when it stops. A no-op until
the `HEALTHCHECKS_PING_KEY` secret is set; set each check's period and grace
by hand after its first ping. → `docs/decisions/watch.md`

## Publishing

Meta Business Suite Planner, manually, is the current path. It is free,
first-party, supports carousels, and has no post cap.

The Instagram Graph API is a later option: free but gated by app review,
requires a Professional account linked to a Facebook Page, uses a two-step
container + publish call, has **no native scheduling endpoint**, and caps at
50 API-published posts per rolling 24 hours. Do not start building against it
without an explicit decision.

## The status-report pillar

Single 1080×1350 humour slides under `STATUS REPORT #NN`, one a day, sent by
`series.yml` and confirmed by `publish.yml`'s poll. Strategy and design are
in `docs/gummietech_status_reports.md`; `python src/series.py` prints the
queue.

- **It is not a `post_type`, and adding one would be the mistake** — it has
  no source to credit and its own locked design system.
- Slides are exported by hand into `series/images/`;
  `!series/images/*.png` in `.gitignore` is what lets them be committed.
- Its callback prefix is `ser:` (reports `published=false`); one poller
  serves both pillars; `sent_at` is not `published_at`; a missing image is
  said in the chat and exits 0, never skips ahead; so is an empty queue.
- **Send a different one today** (`series.yml` with `swap`) sends an
  unnumbered report in place of today's, which loses `sent_at` and goes out
  tomorrow — the numbering is never skipped. `confirm` ignores the
  swapped-out message's ✅ (`stale_series_tap()`).

→ `docs/decisions/status-report-mechanics.md`

## When updating strategy

`docs/gummietech_content_system.md` and this file both describe the project
and can drift. If a change here affects strategy — or vice versa — say so
rather than silently updating one.
