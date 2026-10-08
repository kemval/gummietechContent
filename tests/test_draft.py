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
from datetime import datetime, timedelta, timezone

import pytest

import draft
import papers
import render


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

        monkeypatch.setattr(papers, "fetch_crossref", fake)
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
    named, mentioned = papers.doi_candidates(page)
    assert "10.1038/s41586-026-10968-9" in named + mentioned


def test_trailing_sentence_punctuation_is_not_part_of_the_doi():
    page = "Journal reference: doi:10.1234/abcd.5678."
    named, _ = papers.doi_candidates(page)
    assert named == ["10.1234/abcd.5678"]


def test_the_meta_tag_outranks_a_doi_further_down_the_page():
    page = ('<meta name="citation_doi" content="10.1111/first">'
            '<p>See also 10.2222/second</p>')
    named, mentioned = papers.doi_candidates(page)
    assert named[0] == "10.1111/first"
    assert "10.2222/second" in mentioned


def test_a_weak_cue_does_not_reach_a_footnote_a_page_away():
    """openai.com/index/gpt-6-astra, 2026-10-07: the word "citation" in the
    markup, and one DOI 135k characters later — footnote 7, a musicology
    dataset the model was evaluated on. It was named as the paper, and the
    draft credited its authors for OpenAI's launch."""
    footnote = "10.1145/3625135.3625155"
    page = ('<div data-x="citation"></div>' + "<p>launch copy</p>" * 20000
            + f'<li>7. Gotham et al. <a href="https://doi.org/{footnote}">x</a></li>')
    named, mentioned = papers.doi_candidates(page)
    assert named == []
    assert footnote in mentioned


def test_a_weak_cue_still_names_the_doi_right_after_it():
    page = '<p>Citation: Smith et al. (2026). <a href="https://doi.org/10.1234/near">x</a></p>'
    named, _ = papers.doi_candidates(page)
    assert named == ["10.1234/near"]


# ------------------------------------------------------------ what is coverage

def test_nature_news_is_coverage_though_crossref_files_it_under_nature():
    """Springer Nature mints d-prefixed DOIs for editorial content.

    Nothing about the record's shape separates it from a paper — same venue,
    same type — so the identifier is the only tell.
    """
    news = papers.paper_facts(work("10.1038/d41586-026-02895-6", journal="Nature"))
    paper = papers.paper_facts(work("10.1038/s41586-026-10968-9", journal="Nature"))
    assert papers.is_coverage(news)
    assert not papers.is_coverage(paper)


@pytest.mark.parametrize("venue", ["Physics World", "New Scientist",
                                   "Scientific American"])
def test_named_magazines_are_coverage_even_carrying_an_abstract(venue):
    """Physics World deposits an abstract for every article, which would
    otherwise wave it through as the primary source."""
    assert papers.is_coverage(papers.paper_facts(work("10.1088/x", journal=venue)))


def test_a_matching_title_is_evidence_a_record_is_the_work():
    """2026-09-18: a rule that rejected a record sharing the ingested
    headline threw away the paper on the paper's own page, and credited the
    slides to Wegst et al. (2014) — the first thing its reference list cited.
    """
    facts = papers.paper_facts(work("10.1038/s41586-026-10968-9", journal="Nature",
                                   abstract=""))
    assert not papers.is_coverage(facts)


# ------------------------------------------------------------- resolve_paper

def test_a_named_doi_is_taken_at_its_word(crossref):
    crossref({"10.1126/paper": work("10.1126/paper", journal="Science Advances")})
    facts, warning = papers.resolve_paper(
        '<meta name="citation_doi" content="10.1126/paper">')
    assert warning is None
    assert facts["doi"] == "10.1126/paper"


def test_a_mentioned_doi_older_than_the_story_is_not_the_paper(crossref):
    """2026-09-10: a Research Briefing whose only DOIs were its references
    was about to credit Building and Environment (2012) on a 2026 story."""
    crossref({"10.1016/old": work("10.1016/old", year=2012,
                                  journal="Building and Environment")})
    facts, warning = papers.resolve_paper("<p>see 10.1016/old</p>")
    assert facts is None
    assert "older than the story" in warning


def test_the_coverage_doi_leads_to_the_paper_it_cites(crossref):
    """A news story's Crossref record lists what it covers, and that is
    reachable even when the page itself is paywalled."""
    news = work("10.1038/d41586-026-02895-6", journal="Nature")
    news["reference"] = [{"DOI": "10.1038/s41586-026-10968-9"}]
    crossref({news["DOI"]: news,
              "10.1038/s41586-026-10968-9": work("10.1038/s41586-026-10968-9")})
    facts, warning = papers.resolve_paper(
        '<meta name="citation_doi" content="10.1038/d41586-026-02895-6">')
    assert warning is None
    assert facts["doi"] == "10.1038/s41586-026-10968-9"


def test_a_page_with_its_own_reference_list_is_the_work(crossref):
    """2026-09-28: rohanbansal.com/qorl, the author's own write-up, credited
    Leis et al. (2015) — the first "doi:" in its references. A year test
    alone would have credited the 2026 arXiv preprint further down."""
    refs = [("10.14778/leis", 2015), ("10.14778/revisited", 2025),
            ("10.1145/ibaraki", 1984), ("10.48550/arXiv.2603.07267", 2026)]
    crossref({doi: work(doi, year=year) for doi, year in refs})
    page = "<h2>References</h2>" + "".join(
        f"<p>Someone. A title ({year}). doi:{doi}</p>" for doi, year in refs)
    facts, warning = papers.resolve_paper(page)
    assert facts is None
    assert "reference list" in warning


def test_a_specific_cue_still_names_the_paper_among_references(crossref):
    """Coverage that says "Journal reference:" is not a bibliography just
    because the page also carries other DOIs."""
    crossref({"10.1126/paper": work("10.1126/paper")})
    page = ("<p>Journal reference: doi:10.1126/paper</p>"
            + "".join(f"<p>doi:10.9999/ref{i}</p>" for i in range(5)))
    facts, warning = papers.resolve_paper(page)
    assert warning is None
    assert facts["doi"] == "10.1126/paper"


def test_a_page_with_no_doi_says_so_rather_than_guessing(crossref):
    crossref({})
    facts, warning = papers.resolve_paper("<p>No identifiers here.</p>")
    assert facts is None
    assert "no DOI on the page" in warning


def test_the_crossref_budget_is_not_exceeded(crossref):
    """MAX_CROSSREF_LOOKUPS guards a 15-minute job against a long
    reference list."""
    page = " ".join(f"10.1234/ref{i}" for i in range(40))
    asked = crossref({})
    papers.resolve_paper(page)
    assert len(asked) <= papers.MAX_CROSSREF_LOOKUPS


# ------------------------------------------------------------------ attribution

def test_an_explicit_first_sequence_marker_beats_array_order():
    record = work("10.1/x", authors=())
    record["author"] = [{"family": "Senior"},
                        {"family": "Lead", "sequence": "first"}]
    assert papers.paper_facts(record)["authors"][0] == "Lead"


@pytest.mark.parametrize("authors,expected", [
    (("Solo",), "Solo, Nature (2026)"),
    (("One", "Two"), "One and Two, Nature (2026)"),
    (("One", "Two", "Three"), "One et al., Nature (2026)"),
])
def test_citation_shape(authors, expected):
    assert papers.citation(papers.paper_facts(work("10.1/x", authors=authors))) == expected


def test_a_collaboration_author_list_does_not_overflow_the_prompt():
    """2026-10-02: an ATLAS paper's ~3000 authors pushed the draft past
    Groq's free 8000 tokens-per-minute cap, and daily drafted nothing."""
    names = tuple(f"Author{i}" for i in range(3000))
    facts = papers.paper_facts(work("10.1/x", authors=names))
    facts["abstract"] = "Entanglement between Z bosons."
    text = papers.source_text(facts, "coverage", "")
    assert "Author0" in text and "Author2999" not in text
    assert len(text) < 2000
    assert papers.citation(facts) == "Author0 et al., Nature (2026)"


def test_a_preprint_carries_its_server_where_a_journal_would_be():
    """'Surname et al. (2026)' with no venue reads like an unfinished
    citation."""
    record = work("10.1101/x", journal=None, type="posted-content")
    record["institution"] = [{"name": "bioRxiv"}]
    facts = papers.paper_facts(record)
    assert facts["is_preprint"]
    assert "bioRxiv" in papers.citation(facts)


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


# ---------------------------------------------------------- tech first
# September 2026 shipped almost no AI while 777 tech candidates sat above
# the threshold, because pick_row took the single highest score and AI
# items average two points lower. The account is tech-first; science fills.

HEADER = ["url", "title", "summary", "source", "topic",
          "published", "fetched_at", "status", "score", "notes", "beat"]
COL = {name: i for i, name in enumerate(HEADER)}


def sheet_row(title: str, score: float, topic: str = "general",
              beat: str = "", status: str = "queued",
              age_days: float = 1, published: str | None = None) -> list[str]:
    when = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    return [f"https://x/{title}", title, "", "src", topic,
            when if published is None else published, "",
            status, str(score), "", beat]


def test_a_tech_row_beats_a_higher_scoring_science_row():
    rows = [HEADER, sheet_row("fossil", 9.0, beat="science"),
            sheet_row("agents", 8.0, beat="ai")]
    _, item = draft.pick_row(rows, COL, None)
    assert item["title"] == "agents"


def test_a_row_scored_before_beats_existed_falls_back_to_its_feed():
    rows = [HEADER, sheet_row("fossil", 9.0, topic="biology"),
            sheet_row("chip", 7.5, topic="tech")]
    _, item = draft.pick_row(rows, COL, None)
    assert item["title"] == "chip"


def test_the_beat_outranks_the_feed_topic():
    """A tech feed's battery story is science; Phys.org's AI story is not."""
    rows = [HEADER, sheet_row("battery", 9.0, topic="tech", beat="science"),
            sheet_row("llm", 7.5, topic="general", beat="ai")]
    _, item = draft.pick_row(rows, COL, None)
    assert item["title"] == "llm"


def test_science_is_taken_when_nothing_tech_is_queued():
    rows = [HEADER, sheet_row("fossil", 9.0, beat="science"),
            sheet_row("agents", 9.5, beat="ai", status="drafted")]
    _, item = draft.pick_row(rows, COL, None)
    assert item["title"] == "fossil"


def test_a_tie_goes_to_the_newest_row():
    """2026-10-02: eight tech rows tied at 8.75 and the oldest was drafted."""
    rows = [HEADER, sheet_row("september", 8.75, beat="computing"),
            sheet_row("this-week", 8.75, beat="computing")]
    n, item = draft.pick_row(rows, COL, None)
    assert (n, item["title"]) == (3, "this-week")


def test_a_row_named_by_hand_ignores_the_preference():
    rows = [HEADER, sheet_row("fossil", 9.0, beat="science"),
            sheet_row("agents", 9.5, beat="ai")]
    n, item = draft.pick_row(rows, COL, 2)
    assert (n, item["title"]) == (2, "fossil")


def test_a_short_row_from_a_narrower_sheet_still_reads():
    rows = [HEADER[:-1], sheet_row("chip", 8.0, topic="tech")[:-1]]
    col = {name: i for i, name in enumerate(HEADER[:-1])}
    _, item = draft.pick_row(rows, col, None)
    assert item["title"] == "chip"


def test_each_signal_item_carries_the_subject_its_row_was_on():
    """watch.py says when a Signal item fell back to science; it can only
    read that off the item. An item with no row records nothing."""
    tech, science, unrowed = (pick("https://example.org/a", PAPER),
                              pick("https://example.org/b", PAPER, row=2),
                              pick("https://example.org/c", PAPER, row=3))
    tech["item"]["beat"] = "ai"
    science["item"]["topic"] = "biology"
    post = draft.validate_signal(reply(3), [tech, science, unrowed])
    assert [i.get("beat") for i in post["items"]] == ["ai", "biology", None]


# ------------------------------------------------------------- announcements
# 2026-10-07: the first launch drafted under the relevance lift — OpenAI's
# GPT-6 Astra page, no paper behind it — rendered "Preprint — not yet
# peer-reviewed" on its cover. Not peer-reviewed was true; preprint was not.

def drop_reply(**over):
    return {"post_type": "drop", "domain": "AI models", "colorway": "signal",
            "hooks": ["OpenAI launched a new model"],
            "what_happened": "It happened.", "why_it_matters": "It matters.",
            "the_catch": "Only some users have it.", "caption": "New? Try it?",
            "keywords": ["ai"], "hashtags": ["#gummietech"],
            "alt_text": "A carousel about a launch.", "attribution": "OpenAI",
            "peer_reviewed": False, "announcement": True} | over


def drop_item(url="https://openai.com/index/a-launch"):
    return {"url": url, "source": "OpenAI", "title": "A launch",
            "summary": "A launch."}


def test_a_launch_with_no_paper_is_an_announcement_not_a_preprint():
    post = draft.validate(drop_reply(), drop_item(), None)
    assert post["announcement"] is True and post["peer_reviewed"] is False
    assert render.preprint_claims(post) == 0
    assert render.post_preprint_flag(post) is False


def test_an_announcement_is_never_peer_reviewed():
    post = draft.validate(drop_reply(peer_reviewed=True), drop_item(), None)
    assert post["peer_reviewed"] is False


def test_a_resolved_paper_overrules_the_models_announcement():
    """Code knows better than the model here: a paper is a study, and
    calling it an announcement would hide a preprint flag."""
    preprint = PAPER | {"is_preprint": True}
    post = draft.validate(drop_reply(), drop_item(), preprint)
    assert "announcement" not in post
    assert render.preprint_claims(post) == 1


def test_a_preprint_server_is_never_an_announcement():
    post = draft.validate(drop_reply(), drop_item("https://arxiv.org/abs/2610.00001"),
                          None)
    assert "announcement" not in post
    assert render.post_preprint_flag(post) is True


def test_an_older_post_with_no_announcement_field_reads_as_before():
    post = draft.validate(drop_reply(announcement=False),
                          drop_item("https://example.org/a-story"), None)
    assert "announcement" not in post
    assert render.post_preprint_flag(post) is True


# ------------------------------------------------------------- freshness
# 2026-10-07: the queue held 3,227 rows, mostly from September, ranked by
# score alone. A launch drafted from one — GPT-6 Astra, 34 days old and
# already replaced — said "just launched" on its cover.

def test_a_stale_row_loses_to_a_fresh_one_however_it_scored():
    rows = [HEADER, sheet_row("old launch", 9.5, beat="ai", age_days=34),
            sheet_row("this week", 7.5, beat="ai", age_days=2)]
    _, item = draft.pick_row(rows, COL, None)
    assert item["title"] == "this week"


def test_a_queue_with_nothing_fresh_stops_rather_than_drafting_old_news():
    rows = [HEADER, sheet_row("old launch", 9.5, beat="ai", age_days=34)]
    with pytest.raises(SystemExit, match="last 10 days"):
        draft.pick_row(rows, COL, None)


def test_a_row_named_by_hand_ignores_its_age():
    rows = [HEADER, sheet_row("old launch", 9.5, beat="ai", age_days=34)]
    _, item = draft.pick_row(rows, COL, 2)
    assert item["title"] == "old launch"


def test_a_row_that_cannot_show_its_date_is_not_drafted_as_news():
    rows = [HEADER, sheet_row("undated", 9.5, beat="ai", published="")]
    with pytest.raises(SystemExit):
        draft.pick_row(rows, COL, None)


# ---------------------------------------------------------------- wording
# 2026-10-07, fact-checked test drafts in the new voice: "OpenAI just
# launched GPT-6 Astra" on a 34-day-old launch, and "models you can run"
# about weights Mistral had only promised for the end of the month.

def test_a_cover_line_that_dates_the_story_is_dropped():
    post = draft.validate(drop_reply(hooks=[
        "OpenAI just launched GPT-6 Astra",
        "OpenAI says its model can fill out online forms"]), drop_item(), None)
    assert post["hook"] == "OpenAI says its model can fill out online forms"
    assert "hooks" not in post


def test_an_announcement_cover_line_that_promises_the_reader_is_dropped():
    post = draft.validate(drop_reply(hooks=[
        "Mistral says its model has 1.05 trillion parameters",
        "The open models you can run are getting larger"]), drop_item(), None)
    assert post["hook"] == "Mistral says its model has 1.05 trillion parameters"
    assert "hooks" not in post


def test_an_announcement_cover_line_with_the_makers_figure_as_fact_is_dropped():
    """2026-10-08, Groq: every announcement's third hook stated the maker's
    benchmark as fact, two rounds running ("JPEG XL offers 30-50% better
    compression than JPEG"); the fact-check flagged each one."""
    post = draft.validate(drop_reply(hooks=[
        "EmbeddingGemma 2 improves code performance by 9.92 points.",
        "Google says EmbeddingGemma 2 scores 9.92 points higher on code."]),
        drop_item(), None)
    assert post["hook"] == ("Google says EmbeddingGemma 2 scores 9.92 points "
                            "higher on code.")


def test_you_is_fine_outside_an_announcement():
    post = draft.validate(drop_reply(announcement=False, hooks=[
        "A chip as thin as your fingernail", "Another line"]),
        drop_item("https://example.org/story"), None)
    assert post["hook"] == "A chip as thin as your fingernail"


def test_one_cover_line_is_always_kept():
    """Three lines that all say "just" still make a post: proof.py reports
    the word at the gate, where "just three atoms" can be told apart."""
    post = draft.validate(drop_reply(hooks=["Just three atoms thick",
                                            "Just one layer"]), drop_item(), None)
    assert post["hook"] == "Just three atoms thick"


# ------------------------------------------------- maker announcements
# 2026-10-07. The Signal could not carry a launch: it labels only what code
# can, and only papers and preprint hosts were code's to label. And a launch
# has no DOI, so the twenty rows about GPT-6 Astra — OpenAI's page, InfoQ,
# Hacker News, NVIDIA's blog — were twenty different stories to the guard.

ASTRA = "https://openai.com/index/gpt-6-astra"


def test_the_feeds_declare_where_openai_announces():
    """The prefixes are measured, in the YAML; this keeps them there."""
    assert draft.maker_page(ASTRA)
    assert draft.maker_page("https://www.apple.com/newsroom/2026/10/x/")
    assert not draft.maker_page("https://www.infoq.com/news/2026/09/astra/")
    assert not draft.maker_page("https://openai.com/index")       # the index itself


def test_a_maker_page_with_no_paper_is_an_announcement_whatever_the_model_says():
    post = draft.validate(drop_reply(announcement=False), drop_item(ASTRA), None)
    assert post["announcement"] is True and post["peer_reviewed"] is False


def test_a_maker_blog_describing_a_paper_is_the_paper():
    post = draft.validate(drop_reply(announcement=False),
                          drop_item("https://research.google/blog/a-method/"), PAPER)
    assert "announcement" not in post


def test_a_signal_may_carry_a_launch_and_labels_it():
    post = draft.validate_signal(reply(2), [pick(ASTRA), pick("https://example.org/a", PAPER)])
    first, second = post["items"]
    assert first["announcement"] is True and first["peer_reviewed"] is False
    assert "announcement" not in second
    assert render.preprint_claims(post) == 0


def test_a_signal_still_refuses_a_source_nothing_can_label():
    with pytest.raises(SystemExit):
        draft.validate_signal(reply(1), [pick("https://example.org/no-paper")])


def test_coverage_of_a_posted_launch_is_a_duplicate(tmp_path, monkeypatch):
    """InfoQ's Astra story links OpenAI's page with tracking parameters;
    the post has it without a trailing slash."""
    monkeypatch.setattr(draft, "POSTS_DIR", tmp_path)
    (tmp_path / "2026-10-08-astra.json").write_text(json.dumps(
        {"post_type": "drop", "source_url": ASTRA, "attribution": "OpenAI"}))
    seen = draft.covered_papers()
    page = '<a href="https://openai.com/index/gpt-6-astra/?utm_source=infoq">x</a>'
    links = draft.announced_links(page)
    assert draft.already_covered(None, "https://www.infoq.com/news/x/", seen, links)
    assert draft.already_covered(None, ASTRA + "/", seen)
    assert not draft.already_covered(None, "https://www.infoq.com/news/y/", seen)


def test_sharing_a_maker_is_not_sharing_a_story(tmp_path, monkeypatch):
    """Attribution "OpenAI" is on every OpenAI post; it must not make the
    next OpenAI launch a duplicate of the last."""
    monkeypatch.setattr(draft, "POSTS_DIR", tmp_path)
    (tmp_path / "2026-10-08-astra.json").write_text(json.dumps(
        {"post_type": "drop", "source_url": ASTRA, "attribution": "OpenAI"}))
    seen = draft.covered_papers()
    assert not draft.already_covered(None, "https://openai.com/index/gpt-6-1-sol", seen)
