# Fact-checking a draft

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

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
