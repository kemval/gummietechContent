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
