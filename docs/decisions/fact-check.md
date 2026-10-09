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

## An empty catch instead of an invented one (2026-10-08)

The Groq voice test for PR #20 drafted three posts and all three came back
`FACT-CHECK · BLOCK` on `the_catch`, each invented: "access limited to Google
AI Edge" for an Apache-2.0 model on Hugging Face, "only Chrome supports it"
for JPEG XL (Safari has since 2023), "not mini-scaled" for a nuclear clock
whose paper states a different limit. It was not new: 9 of the 15 drafts
since 2026-09-20 went through fix.yml, most of them for the catch. The prompt
demanded a limitation, and a model given an abstract or a launch page with
none supplies one from general knowledge.

So the prompt now asks for `""` when the text states none, and code holds it
rather than refusing it — a refusal would kill the run before anyone could
press Apply the fixes. `formats.missing_fields()` lets an empty catch through
(present and empty only), the catch slide prints a bracketed held line,
`proof.py` BLOCKs it so the button is withheld even without a fact-check,
and this agent answers every empty catch with a BLOCK and a ready-to-print
replacement from the full source. The same three rows drafted again came back
with three empty catches and no invented ones.

## Replaying past holds before changing the agent (2026-10-09)

`fact-check.md` is the gate's most consequential prompt and nothing tests
it: `tests/` covers pure functions, and an agent run costs Pro quota, so it
cannot go in `check.yml`. But the repo already holds its regression set.
Every `Apply the fact-check to <post>` commit is a fix this agent asked for,
and that commit's parent holds the draft as it was before — a post the agent
once correctly refused to pass. Fourteen of them by this date, covering an
invented catch, a wrong first author, a preprint labelled reviewed
(`3124e59`), a Signal's per-item credit (`eb9214b`), a Breakdown
(`9fa1f8b`) and a run post's `try_it` (`b2b91cf`).

Before merging a change to `.claude/agents/fact-check.md`, replay a few —
those four cover the formats — against the new prompt:

```bash
git log --format=%h --grep='^Apply the fact-check to' |
while read -r c; do
  f=$(git show --name-only --format= "$c" | grep -m1 '^posts/.*\.json$')
  mkdir -p "/tmp/fc-cases/$c"
  git show "$c^:$f" > "/tmp/fc-cases/$c/$(basename "$f")"
  git diff --stat "$c^" "$c" -- "$f" > "/tmp/fc-cases/$c/expected.txt"
  git diff "$c^" "$c" -- "$f" >> "/tmp/fc-cases/$c/expected.txt"
done
```

Then run the agent on `/tmp/fc-cases/<commit>/<post>.json` and compare.
The case passes when the verdict is not PASS and the report names at least
one field the fix changed (`expected.txt`). Two ways it can say nothing:
a source that has since died makes every case an unreadable-source BLOCK,
which proves only that the hold rule works — pick another case; and the
cases are the drafts of their day, so `the_catch` failures from before
2026-10-08 are invented catches, not the empty ones the prompt asks for now.
