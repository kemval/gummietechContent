# The post record, field by field

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

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

`attribution` and `alt_text` are required. `render.py` should refuse to
render a record missing either — attribution is a legal and reputational
requirement, not a nicety. When `draft.py` resolves a DOI it builds
`attribution` from the Crossref author list and discards the model's version,
so a wrong attribution on a drafted post means the DOI was wrong, not the
model.

`beat` is not part of the contract either: `draft.py` copies the drafted
row's beat (or its feed's topic) onto a Drop, and onto each Signal item, so `watch.py` can say when one
fell back to science. The model never supplies it, and nothing renders it.

`hooks` is not part of the contract either. The model returns three cover
lines and `draft.py` keeps them as `hooks`, with the first copied to `hook`,
which is what renders. They exist for the gate: `telegram.py` numbers them in
the message, and `hook.yml` runs `src/hook.py` to put another on the cover,
re-translates, commits, and calls `review.yml`. The alternates are unchecked
until chosen, which is why a swap re-runs the whole review rather than only
re-rendering, and why `fact-check` reports a bad alternate as a FIX naming its
number, never a BLOCK. `hook.py` refuses a post with `published_at`, because
its cover is already fixed on Instagram.

`code_url` is written by code, never by the model: `draft.code_link()` takes
the first `github.com`, `gitlab.com` or `huggingface.co` repo named in the
paper's Crossref abstract or the feed item's summary, which for an arXiv row
is the abstract. It never reads the fetched page, for the same related-stories
rail reason as `DOI_CUES`. Slide 5 and the archive print it.

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

**Three formats added 2026-10-06** (docs §1 has why):

- **`run`** is a Drop plus `try_it`, with `code_url` required. `draft.py
  --run` sets `post_type` itself — the model never chooses it — and only when
  `code_link()` found a repo *and* `papers.fetch_readme()` read its README;
  otherwise the same reply is a Drop. `try_it` may come only from the README,
  which the prompt labels, and `fact-check` reads it again (§7b of the agent).
- **`term`** requires `example_post`, the stem of a post in `posts/` with a
  `published_at`. `render.example_post()` refuses anything else; `site.py`
  skips the page for the same reason. The example's credit and hook are read
  from that post, never retyped, and its source is listed as a second source
  unless it is the term's own.
- **`sheet`** items are strings, `"Term: line"` (`Section.pair`,
  `formats.PAIR`), not objects. A `key` section carries only one field of
  each object through translation, the archive and the gate — the term would
  have been dropped from the Spanish and the page. `unpaired()` refuses an
  item with no separator in render and site.
- **`by_hand`** marks the formats a person writes (Breakdown, term, sheet).
  It is the one answer to "is this a Drop day's Drop" — `daily.yml`'s gate
  and `watch.owes()` — and to "can this be redrafted" — `draft.reject()` and
  the gate's **Another story** button. Each used to compare against
  `"breakdown"`, which a hand-written glossary term dated on a Monday would
  have walked straight through: the 2026-09-28 failure again.

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

**A Signal is drafted, by `draft.py --signal`, on Saturday.** `daily.yml`
asks for a fourth day and runs `--signal` on it; its gate looks for this
ISO week's `signal-week-NN` file rather than today's date, so a roundup
drafted by hand earlier in the week is not drafted twice. It was dispatched
by hand until 2026-09-27, and the week of 09-21 went without one because
nothing asked. It is the same walk down
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
