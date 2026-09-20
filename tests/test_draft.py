"""
draft.py — the paper-resolution half.

Every test here is a post-mortem. The module's own comments name the dates
and the posts that went wrong; these are those cases, frozen so the next
change to a heuristic has to walk past them.

Nothing touches the network: resolve_paper's only I/O is fetch_crossref, and
each test hands it the records it would have fetched.
"""
from __future__ import annotations

import pytest

import draft


@pytest.fixture
def crossref(monkeypatch):
    """Stand in for Crossref, and record what was asked for.

    `works` maps DOI -> the record the API would return; anything else 404s,
    which is the case a page full of dead DOIs exercises.
    """
    def install(works: dict[str, dict]):
        asked: list[str] = []

        def fake(doi: str):
            asked.append(doi)
            work = works.get(doi)
            return (work, None) if work else (None, f"no record for {doi}")

        monkeypatch.setattr(draft, "fetch_crossref", fake)
        return asked

    return install


def work(doi, *, title="A title", authors=("Qin", "Wu"), journal="Nature",
         year=2026, abstract="<jats:p>An abstract.</jats:p>", type="journal-article"):
    """A Crossref record in the shape paper_facts reads."""
    return {
        "DOI": doi,
        "title": [title],
        "author": [{"family": a} for a in authors],
        "container-title": [journal] if journal else [],
        "issued": {"date-parts": [[year]]},
        "abstract": abstract,
        "type": type,
    }


# --------------------------------------------------------------- DOI scraping

def test_doi_is_trimmed_of_the_query_string_it_was_scraped_with():
    """.../10.1038/d41586-026-02895-6?format=refman 404s at Crossref.

    The comment on DOI_RE is explicit that this silently degraded a draft to
    coverage-only, because the 404 looks like an ordinary dead DOI.
    """
    page = '<a href="https://doi.org/10.1038/s41586-026-10968-9?format=refman">cite</a>'
    named, mentioned = draft.doi_candidates(page)
    assert "10.1038/s41586-026-10968-9" in named + mentioned


def test_trailing_sentence_punctuation_is_not_part_of_the_doi():
    page = "Journal reference: doi:10.1234/abcd.5678."
    named, _ = draft.doi_candidates(page)
    assert named == ["10.1234/abcd.5678"]


def test_the_meta_tag_outranks_a_doi_further_down_the_page():
    page = ('<meta name="citation_doi" content="10.1111/first">'
            '<p>See also 10.2222/second</p>')
    named, mentioned = draft.doi_candidates(page)
    assert named[0] == "10.1111/first"
    assert "10.2222/second" in mentioned


# ------------------------------------------------------------ what is coverage

def test_nature_news_is_coverage_though_crossref_files_it_under_nature():
    """Springer Nature mints d-prefixed DOIs for editorial content.

    Nothing about the record's shape separates it from a paper — same venue,
    same type — so the identifier is the only tell.
    """
    news = draft.paper_facts(work("10.1038/d41586-026-02895-6", journal="Nature"))
    paper = draft.paper_facts(work("10.1038/s41586-026-10968-9", journal="Nature"))
    assert draft.is_coverage(news)
    assert not draft.is_coverage(paper)


@pytest.mark.parametrize("venue", ["Physics World", "New Scientist",
                                   "Scientific American"])
def test_named_magazines_are_coverage_even_carrying_an_abstract(venue):
    """Physics World deposits an abstract for every article, which would
    otherwise wave it through as the primary source."""
    assert draft.is_coverage(draft.paper_facts(work("10.1088/x", journal=venue)))


def test_a_matching_title_is_evidence_a_record_is_the_work():
    """2026-09-18: a rule that rejected a record sharing the ingested
    headline threw away the paper on the paper's own page, and credited the
    slides to Wegst et al. (2014) — the first thing its reference list cited.
    """
    facts = draft.paper_facts(work("10.1038/s41586-026-10968-9", journal="Nature",
                                   abstract=""))
    assert not draft.is_coverage(facts)


# ------------------------------------------------------------- resolve_paper

def test_a_named_doi_is_taken_at_its_word(crossref):
    crossref({"10.1126/paper": work("10.1126/paper", journal="Science Advances")})
    facts, warning = draft.resolve_paper(
        '<meta name="citation_doi" content="10.1126/paper">')
    assert warning is None
    assert facts["doi"] == "10.1126/paper"


def test_a_mentioned_doi_older_than_the_story_is_not_the_paper(crossref):
    """2026-09-10: a Research Briefing whose only DOIs were its references
    was about to credit Building and Environment (2012) on a 2026 story."""
    crossref({"10.1016/old": work("10.1016/old", year=2012,
                                  journal="Building and Environment")})
    facts, warning = draft.resolve_paper("<p>see 10.1016/old</p>")
    assert facts is None
    assert "older than the story" in warning


def test_the_coverage_doi_leads_to_the_paper_it_cites(crossref):
    """A news story's Crossref record lists what it covers, and that is
    reachable even when the page itself is paywalled."""
    news = work("10.1038/d41586-026-02895-6", journal="Nature")
    news["reference"] = [{"DOI": "10.1038/s41586-026-10968-9"}]
    crossref({news["DOI"]: news,
              "10.1038/s41586-026-10968-9": work("10.1038/s41586-026-10968-9")})
    facts, warning = draft.resolve_paper(
        '<meta name="citation_doi" content="10.1038/d41586-026-02895-6">')
    assert warning is None
    assert facts["doi"] == "10.1038/s41586-026-10968-9"


def test_a_page_with_no_doi_says_so_rather_than_guessing(crossref):
    crossref({})
    facts, warning = draft.resolve_paper("<p>No identifiers here.</p>")
    assert facts is None
    assert "no DOI on the page" in warning


def test_the_crossref_budget_is_not_exceeded(crossref):
    """MAX_CROSSREF_LOOKUPS guards a 15-minute job against a long
    reference list."""
    page = " ".join(f"10.1234/ref{i}" for i in range(40))
    asked = crossref({})
    draft.resolve_paper(page)
    assert len(asked) <= draft.MAX_CROSSREF_LOOKUPS


# ------------------------------------------------------------------ attribution

def test_an_explicit_first_sequence_marker_beats_array_order():
    record = work("10.1/x", authors=())
    record["author"] = [{"family": "Senior"},
                        {"family": "Lead", "sequence": "first"}]
    assert draft.paper_facts(record)["authors"][0] == "Lead"


@pytest.mark.parametrize("authors,expected", [
    (("Solo",), "Solo, Nature (2026)"),
    (("One", "Two"), "One and Two, Nature (2026)"),
    (("One", "Two", "Three"), "One et al., Nature (2026)"),
])
def test_citation_shape(authors, expected):
    assert draft.citation(draft.paper_facts(work("10.1/x", authors=authors))) == expected


def test_a_preprint_carries_its_server_where_a_journal_would_be():
    """'Surname et al. (2026)' with no venue reads like an unfinished
    citation."""
    record = work("10.1101/x", journal=None, type="posted-content")
    record["institution"] = [{"name": "bioRxiv"}]
    facts = draft.paper_facts(record)
    assert facts["is_preprint"]
    assert "bioRxiv" in draft.citation(facts)
