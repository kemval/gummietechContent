# gummietech — the status-report pillar

The second content stream: one 1080×1350 slide a day of relatable-dev
humour, under a `STATUS REPORT #NN` eyebrow.

`gummietech_content_system.md` is the science pipeline — feeds, scoring,
sourcing, the archive. None of it applies here, which is the reason this file
exists. `CLAUDE.md` §"The status-report pillar" owns the *mechanics* — the
workflow, the callback prefix, the gate — and is not repeated here. This is
the strategy, the contract and the record.

State that changes daily is not written down here either. Ask for it:

```bash
python src/series.py          # what is queued, what went out, in what order
python src/learn.py --series  # what the numbers said about it
```

---

## 1. What it is, and what it is for

The carousels are the reach and credibility pillar. They are slow to make,
sourced, fact-checked, and they say nothing about the person running the
account. A funnel for build services (§0 of the content system) needs the
other half: something daily, cheap to publish, and recognisably a person.

That is this. Its job is **frequency and personality** — the grid looks
alive on the days no paper is worth posting, and the voice is the thing a
prospective client actually responds to.

Three consequences of that job:

- **It is daily.** The Drop is 3×/week because sourcing costs; a status
  report costs an export, so the cadence it can hold is every day.
- **It is never the differentiator.** Dev humour is the most crowded
  category on the platform. This pillar buys presence, not authority. If the
  two ever compete for attention, the carousel wins.
- **It ends in a question, every time.** §6's caption rule, and it matters
  more here: the science posts earn saves, these earn comments and sends.

## 2. Why it is not a `post_type`

`formats.RECORD` requires `attribution`, `source_url` and `peer_reviewed` on
every record, and `render.load_post()` refuses one without them — because a
science post that cannot name its source must not ship. **A status report has
no source to name.** Not a missing field: an absent obligation.

So it gets `src/series.py`, a small stdlib-only manifest module, and nothing
in `src/` renders it. Adding a `post_type` would mean weakening the one check
that protects the other pillar, to serve posts that pillar will never
contain. See `src/series.py`'s docstring, and `CLAUDE.md` for the rest.

## 3. The design system — locked, and separate

Not `templates/tokens.css`. A different system, on purpose: the carousels are
bright field colours behind a 10px ink frame; these are a warm paper page
with a 2px rule. Two systems that read as one account through the wordmark,
the 4:5 canvas and the ink, and nothing else.

| role | value |
|---|---|
| field | `#F3EEE6` warm cream |
| panel / inset | `#FBF8F3` |
| ink (type, rules, borders) | `#2A2420` |
| muted (eyebrow, numerals, sub-labels) | `#6B625A` |
| accent | `#B5533C` terracotta · alternates `#7E8C3A` olive, `#C2528F` magenta, `#2A2420` ink |
| data fills | `#F6D9CF` · `#DDE7CC` · `#E2DEF1` |

- **Type:** Instrument Serif for display (the italic carries the accent
  line), Manrope 400/600/700 for body, JetBrains Mono 500 for the eyebrow,
  numerals and percentages — uppercase, `letter-spacing: 0.08em`.
- **Canvas:** 1080×1350, padding `72px 88px 64px`.
- **Fixed furniture:** eyebrow top-left, 68px logo + `@gummietech`
  top-right; a 2px ink rule above a footer carrying the kicker left and the
  slide count right. Borders are 2px ink, radii `999px` on pills.
- **The accent is a prop**, not a constant — `{{accent}}` with an editor on
  the artboard, so a report is re-tinted without editing markup.

Do not merge the two palettes, and do not copy these values into
`templates/tokens.css`. Nothing in `src/` reads them; they live on the
canvas, and this table is the record of what was chosen.

## 4. Where the slides come from

Designed on a Claude Design canvas — **"GummieTech Status Reports"**,
<https://claude.ai/artifact/HeFZooRs5RodSnqc2MGYLe> — one `.dc.html`
artboard per report under `project/`, plus a `boards` entry in
`project/canvas.json`. The logo is an asset already on that canvas at
`/_blob/8af00af18e01ab3edbd47ce1910859c9`; reference it, never re-upload it.

**The PNG is exported by hand.** A `.dc.html` needs the canvas runtime, so
the repo's Playwright cannot render it — the export is a click in a browser,
and no workflow can do it. `.gitignore` blanket-ignores `*.png`, so
`!series/images/*.png` is the line that lets the exports be committed at all.

**The canvas is not the archive.** As of 2026-09-22 it holds five artboards —
`Main`, `Midnight`, `Learning-07`, `Errors-08`, `Commits-09` — against
fifteen finished slides. The rest were built in earlier sessions that no
longer have a board. So:

> `series/` is the only complete record of this pillar. "Check the canvas for
> the highest built number" answers only for what was built *there*; check
> `series/reports/` for what exists, and `python src/series.py` for where the
> queue has got to.

`07-learning-queue.png` is a local Playwright render of its artboard rather
than a canvas export — 98.5% pixel-identical, antialiasing only.

## 5. The numbering contract

The sequence is public. A follower reads `#NN` as an ongoing log, so the
numbers carry three promises:

1. **No gaps.** A number nothing claims reads as posts gone missing. The set
   has had a hole once — finished slides ran 02–06 then 10–13, and #07, #08
   and #09 were built to close it. `tests/test_series.py` is that case.
2. **No renumbering a live report.** What is posted is posted; a number
   already on the grid cannot be reused, even for a better slide.
3. **In order, no skipping.** `next_unsent()` stops at the next report
   whether or not its image exists, rather than sending the one behind it.

**Posted so far:** #01, #02, #03, and the unnumbered *support-system* report,
which lives on the canvas as `Main.dc.html` / `Midnight.dc.html` as a record
and must never be reused as a future number. Posting resumes at **#04**.

**The unnumbered prototypes** carry an eyebrow instead of a number — `LIVE
FEED`, `SELF AUDIT`, `HOUSE RULES`, `BEHIND THE SCENES`. They are real posts
with no place in the run; `order_key()` sorts them after the numbered queue,
and `missing_numbers()` ignores them. The varied labels read as range rather
than as a break in the series.

## 6. The modules, and why they rotate

A report is built from a layout module. The six in use:

| module | what it is | built |
|---|---|---|
| `cards-4` | four labelled cards | 6 |
| `pills` | a ranked or sequential pill list | 2 |
| `bars` | labelled progress bars with percentages | 2 |
| `timeline` | timestamped entries down a rule | 2 |
| `cards-6` | six-up grid | 1 |
| `pills-icons` | pills with icons | 1 |

**Neighbouring reports should not share a module.** `render.vary()` one
pillar down: two carousels in the same field read as one post in the grid,
and two reports in the same layout read the same way. The numbering already
gets bent for it — the commit-times timeline was numbered **#09 rather than
#08** to put three days and two other modules between it and #06's, and its
commit messages were rewritten so none was borrowed.

Nothing enforces this. `python src/series.py` reports a run of repeats and
moves on, because a repeated layout is cosmetic and withholding a send over
one teaches exactly the reflex the human gate depends on nobody having.

`learn.py --series` groups by `module` and `eyebrow` rather than
`post_type`/`colorway`/`domain`, because those are what vary here. "Which
module earns another ten" is §8's cut-the-weakest-format decision, one pillar
down.

## 7. Captions

§6 of the content system owns the rules and they apply unchanged: first line
is SEO, 3–5 hashtags, question at the end, reply to every comment in the
first hour.

**The record's `caption` and `hashtags` are canonical.** `telegram.py` sends
`caption_text()` into the chat pre-formatted — caption, blank line, tags —
so it is pasted rather than retyped on a phone at 7am.
`~/Desktop/files/status-report-captions.md` is superseded as a caption
source; what was worth keeping from it is §10 below.

Two differences from the carousels, both because there is no source:

- **No `alt_text` field, and that is a gap, not a decision.** The carousels
  require alt text; these records have none, so it is typed into Instagram by
  hand or not at all. Worth closing when the pillar next gets code.
- **No archive page.** `site.py` reads `posts/` and nothing else, which is
  why a status-report tap reports `published=false` — see `CLAUDE.md`. There
  is no link in the caption for these.

## 8. The set as built

Fifteen slides, all exported and committed, as of **2026-09-22**. This is
what exists; `python src/series.py` is what says where the queue has got to.

| # | title | module |
|---|---|---|
| 04 | my current work-life balance | `bars` |
| 05 | my developer personality traits | `cards-4` |
| 06 | my git commit history | `timeline` |
| 07 | my current learning queue | `bars` |
| 08 | error messages, ranked by pain | `pills` |
| 09 | my commit times vs. my sleep | `timeline` |
| 10 | my emergency developer kit | `cards-6` |
| 11 | things keeping my codebase alive | `cards-4` |
| 12 | things I say while coding | `pills` |
| 13 | my computer science survival kit | `pills-icons` |
| — | `STATUS REPORT` · my debugging process | `cards-4` |
| — | `LIVE FEED` · tabs open right now | `cards-4` |
| — | `SELF AUDIT` · red flags in my own code | `cards-4` |
| — | `HOUSE RULES` · my AI buddy is not allowed to | `cards-4` |
| — | `BEHIND THE SCENES` · what will run this account | `cards-4` |

## 9. Runway, and the one thing that is wrong with it

Fifteen slides, one a day, is **fifteen days** — through roughly
**2026-10-07** from a 09-23 start. After that, #14 onward is new work.

**The bottleneck is the export, not the writing.** A record is a minute; an
artboard and its export are the cost. So build in batches — five artboards in
one sitting, fortnightly — rather than drafting daily, because a daily
obligation to sit at a browser is the thing that quietly ends a daily series.

**The prototypes run as a five-day block of one layout.** They sort last and
they are all `cards-4`, so days 11–15 are five identical layouts in a row —
which contradicts §6's rotation rule *and* the caption file's own "post them
between numbered reports". `python src/series.py` prints this run every time
it is asked. Two honest ways out, and it is a choice rather than a bug:

- **Interleave them** — give a prototype a numbered slot in the queue when
  the module before it differs. This is the cheaper fix and it spreads the
  varied eyebrows across the run, which is what they are for.
- **Build #14 onward first**, so the block is never reached in one piece.

Do not "fix" it by numbering the prototypes. They are posted without numbers
by design, and a number assigned now is a promise about a sequence that has
already been published.

## 10. Topic bank for #14 onward

Chosen so the layout keeps rotating rather than shipping card grid after card
grid.

| idea | module |
|---|---|
| my localhost graveyard — abandoned side projects | `cards-6` |
| how I name variables — `userData` → `x2_FINAL` | `pills` |
| things I swore I'd learn this year | `bars` |
| stages of a code review | chat bubbles — new module |
| what I googled this week | search-bar list — new module |
| my browser at 2am vs. at 9am | two-column split — new module |

Three of those want a module that does not exist yet, which is deliberate:
the rotation runs out of variety around twenty reports otherwise.

## 11. Sibling series — ranked

The pillar is a design system and a queue, not one joke format. Everything
below reuses both. None of it is built; this is the shortlist to pick from,
in the order it should be picked.

### 1. `CHANGELOG` — weekly, Friday

What actually shipped on the pipeline this week. **Its job is conversion,
not reach**, which makes it the only candidate here that does a job nothing
else currently does: The Build (§1, 2×/week reels) is the conversion pillar
and no reel has been made, because the camera is the expensive part. A
changelog slide is the still-frame stand-in — build-in-public at the cost of
an export.

Material already exists and is true: the git log, and `CLAUDE.md`'s record of
why each decision was made. Module: `timeline` or `pills`.

### 2. `POST-MORTEM` — fortnightly

One thing that broke, and what it taught. The material is already written
down: `tests/` is nine real failures by its own entry criterion — a
reference-list author credited on a 2026 story, five of a Breakdown's eight
slides sent to the gate, nine metrics answers dropped in silence.

Specific, true, and nobody else in the category posts it. It is the earnest
sibling of the humour series and the strongest save candidate on this list.
Needs no code at all: an eyebrow and an artboard.

### 3. `FIELD NOTES` — weekly

One genuinely useful thing learned, no punchline. **Scope it to first-person
craft** — what was tried, what worked — and not to general fact. A factual
claim re-imports §7's citation burden, and a post that needs a source belongs
in the other pillar where the fact-check lives.

### 4. `COST REPORT` — monthly

The $0 bill, itemised: Actions minutes used against the free allowance,
Gemini/Groq calls made against the daily cap, storage, **total $0.00**. On
brand for the funnel, genuinely unusual, and the numbers already exist. One
slide a month, `bars` or `pills`.

### Deferred

Reader Q&A (`ASK THE BOT`) needs an audience that sends questions — revisit
when the DMs justify it. `SPEC SHEET` overlaps `FIELD NOTES` and would split
the same register in two.

### What a second series costs in code

`order_key()` and `next_unsent()` assume **one** numbered sequence, so
`CHANGELOG #01` would sort ahead of `STATUS REPORT #04` and go out next. A
second numbered series turns the queue from one ordered list into "which
series is due today", touching `order_key()`, `next_unsent()` and
`series.yml`'s gate. Everything else already carries it: `label()` prints the
eyebrow with the number, `learn.py --series` groups by `eyebrow`, and
`confirm()` finds a record by stem whatever series it belongs to — so a
sibling is measurable from its first post.

**Cadence: one slide a day across the whole pillar, not one per series.** The
daily rhythm is what is working; a second daily series halves each one's
runway and doubles the export sitting.

## 12. What this pillar deliberately does not do

Recorded as decisions, so none of them is re-proposed as an oversight.

- **No fact-check, no `proof.py`.** There is no source to verify and no
  measured layout to check — the slide is a finished PNG by the time anything
  in the repo sees it.
- **No web archive.** `site.py` reads `posts/`; a report tap reports
  `published=false` precisely so a rebuild does not produce byte-identical
  HTML every day.
- **No auto-publish.** Layer 5 applies here exactly as it does to a Drop.
  `sent_at` means the bot showed it to you; `published_at` means you put it
  on Instagram. Different facts, hours apart.
- **No runway alert.** `watch.py` only asks about obligations that have
  already come due; an empty queue three days from now has not. Revisit if a
  runway actually runs out unnoticed — that is the evidence the check would
  need.
