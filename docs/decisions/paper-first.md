# Drafting from the paper

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

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

## The limits come from the body (2026-10-08)

An abstract sells the result; the limits live in the discussion. Drafted
from the abstract, the nuclear-clock draft invented "not mini-scaled", while
the paper's own limit — runs on different days agreed only to 5×10⁻¹³ — sat
in the body. So for the one paper a Drop is drafted from, `fetch_limits()`
fetches the paper (`https://doi.org/<doi>` asked for HTML; arXiv DOIs at
`/html/`) and `limit_sentences()` keeps only sentences carrying a limit cue,
ranked by cues, in reading order, up to `LIMITS_CHARS` (1500).

- **Sentences, not the paper.** Groq's free tier allows 8000 tokens a minute;
  the prompt alone is ~2500 and a paper 25–100k characters.
- **A cue picks, a hedge only ranks.** "uncertainty", "however", "cannot"
  alone filled the budget with the topic of an arXiv paper about uncertainty.
- **doi.org needs `Accept: text/html`.** With the feeds' RSS header it
  redirects to Crossref's API and answers 406.
- **Degrades to the abstract.** Measured on the archive's DOIs: Nature served
  the full text; Wiley, Science and Elsevier refused the bot. Then the prompt's
  empty catch and the fact-check take over, as before.
- **Drop only.** Not the candidates walked past, not a Signal's five.

The nuclear-clock row redrafted with it came back with the paper's own limit
as its catch, and the prompt stayed under the cap.
