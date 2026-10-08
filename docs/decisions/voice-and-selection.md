# Voice and selection: what gets picked, and how it is told

Decided 2026-10-07. CLAUDE.md states the rules; this is why.

## What prompted it

The owner reads The Rundown AI, Ben's Bites, TLDR AI and Techpresso, and asked
for gummietech to feel like them. Asked what exactly, they named two things:
**the information** those digests choose, and **how they tell it**. They tell
it plainly, close to the reader, so the reader feels a step ahead.

The account was built to do the opposite on both counts:

- **Selection.** `score.py` scored "product launches with no technical
  substance" at 3 or below on every axis, and its four axes (novelty, visual,
  explain, surprise) never asked whether a reader would care. The week this
  was decided, TLDR AI led with Mistral Large 4, an OpenAI API, Gemini 4 and
  GPT-6.1. A launch like those could not reach the queue. A reverse-engineered
  iPod headset protocol could.
- **Voice.** The prompt said "smart non-expert" and nothing else about how to
  sound, so the free-tier model wrote abstracts. The Drop of 2026-10-05 opened
  with "Hemant reverse-engineered Mikey's I2C resistive button protocol…".
  Every word of that was true, and almost nobody would stop scrolling for it.

## What changed

**Relevance, as a lift.** `score.py` asks in the same call for `relevance`:
"would a curious person who uses technology want to know this today?" It is
not averaged in. At `LIFT_AT` (8) or above it *is* the item's score; below
that, the mean of the four original axes stands. So it can raise a launch
and never sink a finding. The threshold is still 7.0. It is stored in
`notes` next to the axes (`n6 v3 e7 s6 r8`), so the sheet needed no new
column.

Two other shapes were measured first on 2026-10-07, on the same rows with
Groq's `gpt-oss-120b`, and both were rejected:

| shape | 60 recent rows queued | lab launches past 7 |
|---|---|---|
| old prompt | 10–19 | 1 of 40 |
| relevance as a fifth averaged axis | 2 | 1 of 40, while customer stories rose to 6–6.4 |
| relevance in place of `visual` | 1 | 0 of 40 |
| **relevance as a lift (chosen)** | **5** | JPEG XL in Chrome lifted in; no marketing lifted |

The model gives nearly everything a relevance of 4–7, so any average with it
drags the queue down without letting launches through. As a lift, only the
8s count.

What the lift run also showed: six narrow biophysics preprints fell out of
the queue. The formula does not touch them; the model scores their other
axes lower once the prompt talks about relevance. That is the direction the
owner asked for, so it stays, but nothing was designed to do it.

**Scores are noisy, and the batch matters.** The same OpenAI GPT-6 Astra
announcement got relevance 8 in a batch of four and 2 in a batch of fifteen
customer stories, where the model read everything as marketing. Production
batches are mixed feeds, which is the case that worked. Rows scored before
2026-10-07 keep their old score. `score.py` only ever scores `new` rows, so
the 3,227-row queue of that date turns over only as ingest adds new items.

**Launches are news.** A model, feature or tool people can use scores on what
it does and how many people it reaches, as long as the item states a concrete
capability. These stay at 3 or below: funding and acquisitions, hiring,
firings and personnel news, lawsuits and company drama, opinion, listicles,
awards, conferences, and announcements that name no capability (marketing).

**Drama stays out on purpose.** The digests cover firings and lawsuits. We do
not: they are the stories we can least verify against a primary source,
they go stale fastest, and they are the ones a wrong detail costs the most
on.

**Primary sources for launches.** A lab's own announcement is what
fact-check verifies a launch against, so the labs' feeds are the intake:
Mistral was added (`feeds/tier1_primary.yaml`). Anthropic and Meta AI publish
no feed. That was checked on 2026-10-07 and recorded in that file's header,
and their launches still arrive through Hacker News 200+. With no DOI,
`draft.py` drafts from the announcement with its usual warning: paper-first
degrades, it does not fail.

**Footnotes are not the paper.** The first launch drafted under this
change was credited to "Gotham et al., Digital Libraries for Musicology
(2023)". `openai.com/index/gpt-6-astra` said "citation" in its markup.
`doi_candidates()` treated that as a cue and took the first DOI after it:
footnote 7, 135k characters later, a dataset the model was evaluated on.
Launch pages cite in footnotes, so a weak cue now only names a DOI within
`WEAK_CUE_REACH` (2,000 characters) of it. With that, the page falls back
to drafting from the announcement, credited to OpenAI.

**Unreviewed is not preprint.** The same draft's cover said "Preprint —
not yet peer-reviewed". `peer_reviewed` had two values, and a company
launch is neither a paper nor a preprint. Before this change almost no
launch reached a draft, so nobody noticed. Now every launch would have been
mislabelled. The fix is a third state, `announcement`, decided by one
function (`formats.preprint()`) that the slides, proof, reel, archive and
gate all read. The model proposes it; code drops it for a resolved paper or
a preprint host; fact-check checks it both ways. The cover then says what
the source is ("Announcement — not a peer-reviewed study"), not only what
it is not.

**Only fresh news is drafted.** The fact-check of that first draft also
caught "just launched" on a launch from September 3, which OpenAI had
already replaced. `pick_row()` ranked the queue by score alone, and the
queue held 3,227 rows, mostly from September. So a launch reached a draft
a month late, and a reader who follows us to be ahead would have been
behind. A queued row whose story is older than `MAX_STORY_AGE_DAYS` (10)
is no longer chosen. The age is read from `published`, else `fetched_at`,
and a row with neither is too old. The rows stay queued, and `--row` is
still the override. 10 days rather than ingest's 7-day window, because the
window measures the story at fetch and this measures it at drafting. The
rule lives in `ingest.py` next to that window, so `draft.py` and
`watch.py`'s queue check count the same rows. On the live sheet that day,
760 of 3,230 queued rows were fresh, and the pick moved from a September
row to a story published that morning. The voice guide also gained "no
time words", since the model cannot know today's date.

**What the model would not follow, code enforces.** The voice was tested
on the production models before it shipped. Three launches were drafted on
Gemini and each draft was fact-checked, in three rounds; rules were moved
from the guide into the prompt's own rules between rounds. Attribution
("OpenAI says") and the time words were fixed by moving them into the
prompt. Lost qualifiers, invented causes and "you can" kept coming back in
new places each round: one BLOCK and two FIXes in the second round, and
visible errors in the third. A free-tier model does not follow fifteen
rules reliably, and more rules gave less each time. So the two rules a word
list can check live in `src/wording.py`. `draft.py` drops a cover line with
a dating word, or with "you" in an announcement; `proof.py` reports any
left on a slide or in the caption as a FIX, which reaches the gate. A
question is exempt from the "you" rule, because every caption ends by
asking the reader one; the first version of the check flagged all three
captions. The word list is narrower than the guide's. Run over the 35 posts
in `posts/`, the guide's full list flagged 9, nearly all wrongly: "ice can
now be 3D printed", "today's quantum computers", and the Signal's own "this
week". Without "now", "today" and "new", and with "this week" allowed in a
roundup, it flags 2: "AI code generation just beat human experts", which
is right, and "just 100 Myr after the Big Bang", where "just" means "only".
That is why it is a FIX. Everything else is judgement and stays with fact-check, which
caught every error in all three rounds before anything reached a slide.

**Code labels a launch when it can.** The announcement state started as
the model's proposal. That left the Signal unable to carry a launch,
because it labels only what code can, and it left a launch's label resting
on the model. Each newsroom feed now declares the URL prefixes where its
company announces (`announces`, measured from the sheet). A page under one
of them with no paper is an announcement by code, the twin of
`PREPRINT_HOSTS`. On the live sheet, every recent maker-page row without a
paper was labelled so, and the two that describe a paper (PNAS, Science
Robotics) stayed papers. The Signal prompt marks those sources, so each
item attributes its maker's numbers. The same prefixes give a launch its
duplicate key: see `dedup.md`.

**The voice lives in `docs/voice.md`.** It is a doc rather than prompt text
so a person can change how the account sounds without touching code.
`draft.voice()` pastes it into the Drop, run and Signal prompts, from its
first `##` heading on. Pasting it was not enough on its own: the Drop
prompt's field instructions ("name the bottleneck it removes", "the
assumption it breaks") outranked it, and the first test drafts came back in
the old register. Those instructions were rewritten in the same voice. The rewrite then contradicted the prompt's own fact rules, and the 2026-10-08 Groq round showed where: hook 2 ("start from something the reader knows") came back as analogies ("ticks like a tiny atom"), hook 3 ("the number made concrete, 'as thin as'") as converted or misread figures, and `why_it_matters` ("what changes for a person") as uses a physics paper never names, three BLOCKs on one draft. The field instructions now ask for the thing the story is about, the number as stated, and what the text says it changes; nothing was added to the rules. The next round drew no BLOCK outside an empty catch. `weekly.py`'s brief tells Claude to read it before
writing a term or a Breakdown. A missing file stops the draft with the
command that restores it, rather than drafting in no voice at all.

## What did not change

- **Facts.** Every prompt rule that says a claim must come from the source
  still outranks the voice, and both prompts say so in those words. The
  relatable angle has to be in the source too. "Do not invent a reader
  consequence" is the voice's own first exception, because "what changes for
  you" is exactly where a model invents.
- **The catch, fact-check, the human gate, and `pick_row()`'s tech-first
  preference.** The account is still credible first. It is now credible
  about the things its readers actually follow.
- **Word limits.** Plainer is not longer.

## Settled by

`learn.py`. Saves and shares on Drops drafted after 2026-10-07 against the
ones before. If launches drag the numbers down, the threshold or the
relevance wording is the thing to change, not the voice file.
