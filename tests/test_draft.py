"""
draft.py — the paper-resolution half.

Every test here is a post-mortem. The module's own comments name the dates
and the posts that went wrong; these are those cases, frozen so the next
change to a heuristic has to walk past them.

Nothing touches the network: resolve_paper's only I/O is fetch_crossref, and
each test hands it the records it would have fetched.
"""
from __future__ import annotations

import json

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


# --- the Signal: five sources in one prompt -------------------------------
#
# A roundup moves attribution, source_url and peer_reviewed onto each item,
# so everything draft.py owns in code it now has to own five times over. The
# index into the prompt is the only thing relating a claim to its credit.

def pick(url, paper=None, row=1):
    return {"row": row, "article": "text", "paper": paper,
            "item": {"url": url, "source": "example.org", "title": "A story",
                     "summary": "A summary.", "score": 8}}


def reply(n, **over):
    return {"domain": "This week", "colorway": "orbit",
            "hook": f"{n} results you missed", "caption": "Which one?",
            "keywords": ["science"], "hashtags": ["#science"],
            "alt_text": "A roundup of results.",
            "items": [{"claim": f"Result {i}.", "attribution": f"Model {i}"}
                      for i in range(1, n + 1)]} | over


PAPER = {"doi": "10.1000/real", "authors": ["Alvarez", "Bo", "Chen"],
         "journal": "Nature", "year": "2026", "is_preprint": False,
         "abstract": "", "title": "The real paper"}


def test_crossref_overrides_the_models_credit_per_item():
    """The same override a Drop gets, applied to the item rather than the
    post — coverage quotes whoever gave the interview."""
    post = draft.validate_signal(
        reply(1), [pick("https://example.org/a", PAPER)])
    assert post["items"][0]["attribution"] == "Alvarez et al., Nature (2026)"
    assert post["items"][0]["doi"] == "10.1000/real"


def test_a_preprint_host_forces_one_items_flag_down_and_not_the_others():
    """§7.2 is a per-claim rule. One arXiv link among four journal papers
    labels one slide, not all five and not none."""
    post = draft.validate_signal(
        reply(2), [pick("https://arxiv.org/abs/2609.00001"),
                   pick("https://example.org/b", PAPER, row=2)])
    assert [i["peer_reviewed"] for i in post["items"]] == [False, True]


def test_a_reply_of_the_wrong_length_is_refused_not_zipped():
    """Order is the only link between a claim and its credit. Zipping a
    short reply against the picks would put someone else's name under a
    result on a public slide."""
    with pytest.raises(SystemExit, match="2 sources went in and 1 came back"):
        draft.validate_signal(reply(1), [pick("https://example.org/a", PAPER),
                                         pick("https://example.org/b", PAPER)])


def test_an_item_nothing_can_label_is_a_stop():
    """No DOI and not a preprint host means nothing in code knows, and the
    model is not allowed to decide this one."""
    with pytest.raises(SystemExit, match="Nothing could settle peer_reviewed"):
        draft.validate_signal(reply(1), [pick("https://example.org/a")])


def test_a_signals_items_register_in_the_duplicate_guard(tmp_path,
                                                         monkeypatch):
    """covered_papers read only the top level, where a Signal keeps nothing.
    Five stories went into a roundup that the next --signal run could not
    see, and would have picked straight back out of the queue."""
    monkeypatch.setattr(draft, "POSTS_DIR", tmp_path)
    (tmp_path / "2026-09-20-signal-week-38.json").write_text(json.dumps({
        "post_type": "signal", "hook": "h", "alt_text": "a",
        "items": [{"claim": "c", "attribution": "Alvarez et al., Nature (2026)",
                   "source_url": "https://example.org/a", "doi": "10.1000/real",
                   "peer_reviewed": True}]}))

    seen = draft.covered_papers()
    assert draft.already_covered(PAPER, "https://elsewhere.test/x", seen)
    assert draft.already_covered(None, "https://example.org/a", seen)
