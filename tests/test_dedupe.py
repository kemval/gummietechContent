"""
The duplicate guard — draft.py's other half.

The sheet is deduplicated by URL and a story is not a URL: 45 feeds cover one
press release and the siblings of the drafted row stay queued forever. On
2026-09-17 the top row of a 1440-row queue was the paper published that
morning.
"""
from __future__ import annotations

import pytest

import draft

TIDES = ("https://physics.stackexchange.com/questions/121830/"
         "does-earth-really-have-two-high-tide-bulges-on-opposite-sides")


@pytest.fixture
def covered(monkeypatch, posts_dir):
    directory, write = posts_dir
    monkeypatch.setattr(draft, "POSTS_DIR", directory)
    return write


def test_a_post_is_found_by_its_doi(covered):
    covered("2026-09-18-x.json", doi="10.1038/s41586-026-10968-9",
            attribution="Qin et al., Nature (2026)", source_url="https://n/1")
    paper = {"doi": "10.1038/s41586-026-10968-9", "authors": [], "journal": "",
             "year": None}
    assert draft.already_covered(paper, "https://other", draft.covered_papers())


def test_an_older_post_with_no_doi_is_still_found_by_its_citation(covered):
    """`doi` was not written until this guard needed it, so the citation is
    the key that works on the fifteen posts that predate it."""
    covered("2026-09-14-x.json", attribution="Qin et al., Nature (2026)",
            source_url="https://n/1")
    paper = {"doi": "10.1/unseen", "authors": ["Qin", "Wu", "Li"],
             "journal": "Nature", "year": 2026}
    assert draft.already_covered(paper, "https://other", draft.covered_papers())


def test_an_evergreen_candidate_is_found_by_its_url(covered):
    """The bug this fixes: the evergreen path fetches no page, so it resolves
    no paper and neither of the other two keys can ever be formed. `--evergreen`
    would have re-drafted the tides post, published 2026-09-15 and still #1 in
    the queue."""
    covered("2026-09-15-tides.json", attribution="Laplace", source_url=TIDES)
    assert draft.already_covered(None, TIDES, draft.covered_papers()) \
        == "2026-09-15-tides.json"


def test_an_unposted_subject_is_not_covered(covered):
    covered("2026-09-15-tides.json", attribution="Laplace", source_url=TIDES)
    assert draft.already_covered(None, "https://example.org/new",
                                 draft.covered_papers()) is None


def test_a_malformed_post_does_not_take_the_guard_down(covered, posts_dir):
    directory, _ = posts_dir
    (directory / "broken.json").write_text("{not json")
    covered("2026-09-15-tides.json", attribution="Laplace", source_url=TIDES)
    assert draft.already_covered(None, TIDES, draft.covered_papers())


# ------------------------------------------------------- walking the queue

QUEUE = """# Evergreen queue

### 1 · 8.50 · `orbit` — The tidal bulges that don't exist

**Hook** — The two bulges do not exist.
**Source** — [Physics SE](URL) · **attribute to** Laplace
**Why it matters** — Tides are a wave problem.
**The catch** — Newton's forcing function is right.

### 2 · 8.25 · `bloom` — Corals stir their own water

**Hook** — Corals beat cilia to stir water.
**Source** — [Quanta](https://www.quantamagazine.org/corals)
**Why it matters** — Active ventilation, not diffusion.
**The catch** — The bleaching link is not demonstrated.
""".replace("URL", TIDES)


@pytest.fixture
def queue(monkeypatch, tmp_path):
    # Under a REPO_ROOT of its own: the exhausted-queue message prints the
    # path relative to it, and relative_to raises on anything outside.
    docs = tmp_path / "docs"
    docs.mkdir()
    path = docs / "evergreen_queue.md"
    path.write_text(QUEUE)
    monkeypatch.setattr(draft, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(draft, "EVERGREEN_QUEUE", path)
    return path


def test_the_top_candidate_is_taken_by_default(queue):
    assert draft.evergreen_candidate(0)["rank"] == 1


def test_a_skipped_rank_is_walked_past(queue):
    """`--evergreen` with no number means "the best one left", so a covered
    candidate is skipped exactly as a covered sheet row is."""
    assert draft.evergreen_candidate(0, frozenset({1}))["rank"] == 2


def test_naming_a_rank_ignores_the_skip_set(queue):
    """Naming a candidate by hand is the override, same as --row."""
    assert draft.evergreen_candidate(1, frozenset({1}))["rank"] == 1


def test_an_exhausted_queue_says_what_to_do(queue):
    with pytest.raises(SystemExit) as exit:
        draft.evergreen_candidate(0, frozenset({1, 2}))
    assert "evergreen-scout" in str(exit.value)


def test_the_arxiv_id_wins_over_the_coverage_link(queue, tmp_path, monkeypatch):
    """A preprint row cites a bare arXiv id and links only the coverage.
    Taking the first link would put a magazine URL in source_url and leave
    PREPRINT_HOSTS silent on a preprint."""
    path = tmp_path / "docs" / "q.md"
    path.write_text(
        "### 9 · 8.00 · `signal` — The quantum benchmark that fell\n\n"
        "**Hook** — It fell to a laptop.\n"
        "**Source** — arXiv:2601.04621 — coverage: [Quanta](https://quanta.org/x)\n"
        "**Why it matters** — It moves the goalposts.\n"
        "**The catch** — Only the ground state.\n")
    monkeypatch.setattr(draft, "EVERGREEN_QUEUE", path)
    item = draft.evergreen_candidate(9)
    assert item["url"] == "https://arxiv.org/abs/2601.04621"
    assert any(host in item["url"] for host in draft.PREPRINT_HOSTS)
