"""
score.py — reading what the model sent back.

A batch that fails to parse costs eighteen items of the day's quota, so the
shapes a free-tier model actually returns are the ones worth pinning down.
"""
from __future__ import annotations

import pytest

import score


def test_a_plain_array_is_read():
    assert score.parse_scores('[{"id": 1, "novelty": 8}]') == [{"id": 1, "novelty": 8}]


def test_a_results_object_is_read():
    """Models wrap arrays in an object about as often as not."""
    assert score.parse_scores('{"results": [{"id": 1}]}') == [{"id": 1}]


def test_a_fenced_reply_is_read():
    assert score.parse_scores('```json\n[{"id": 1}]\n```') == [{"id": 1}]


@pytest.mark.parametrize("reply", ["", "   ", "Sure! Here are the scores:",
                                   "{}", '{"scores": []}', "null"])
def test_anything_unreadable_is_an_empty_batch_not_a_crash(reply):
    """The run must survive one bad batch: score.py writes back after every
    batch so the work already paid for is safe in the sheet."""
    assert score.parse_scores(reply) == []


def test_overall_is_the_mean_of_the_four_axes():
    assert score.overall({"novelty": 8, "visual": 7, "explain": 9,
                          "surprise": 8}) == 8.0


def test_a_missing_axis_counts_as_zero_rather_than_inflating_the_mean():
    """A model that omits an axis must not produce a score that clears
    THRESHOLD on three axes."""
    assert score.overall({"novelty": 10, "visual": 10, "explain": 10}) == 7.5


def test_relevance_lifts_a_launch_the_axes_hold_down():
    """2026-10-07: OpenAI's own GPT-6 Astra announcement scored 3 — the
    launch the AI digests led with that week could not reach the queue."""
    assert score.overall({"novelty": 5, "visual": 3, "explain": 6,
                          "surprise": 4, "relevance": 9}) == 9.0


def test_relevance_never_sinks_a_finding():
    """Measured the same day: averaged in, relevance cut the queue from 14
    to 1 of 60 rows. A science result keeps the score it always had."""
    assert score.overall({"novelty": 8, "visual": 7, "explain": 9,
                          "surprise": 8, "relevance": 4}) == 8.0


def test_an_out_of_scale_relevance_cannot_outrank_every_finding():
    assert score.overall({"novelty": 2, "visual": 2, "explain": 2,
                          "surprise": 2, "relevance": 15}) == 10.0


def test_string_scores_are_accepted():
    assert score.overall({a: "8" for a in score.AXES}) == 8.0


def test_the_threshold_matches_the_documented_one():
    """docs §2: only items scoring >= 7 surface."""
    assert score.THRESHOLD == 7.0


def test_a_beat_off_the_list_is_stored_blank():
    """draft.py selects on this column; a word the model invented must not
    quietly count as a subject, or as science."""
    assert score.beat_of({"beat": "AI"}) == "ai"
    assert score.beat_of({"beat": "machine learning"}) == ""
    assert score.beat_of({}) == ""


def test_every_sheet_column_is_in_an_ingested_row(monkeypatch):
    """ingest appends [item[c] for c in COLUMNS]; adding `beat` to COLUMNS
    without adding it to the row would have failed every ingest with new
    items (caught before it ran, 2026-09-27)."""
    import ingest

    class Resp:
        status_code = 200
        content = (b"<rss><channel><item><title>A robot</title>"
                   b"<link>https://x/1</link></item></channel></rss>")

    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(ingest, "pace_host", lambda url: None)
    items, error = ingest.fetch_feed({"name": "t", "url": "https://x/feed"})
    assert error is None and items
    assert set(ingest.COLUMNS) <= set(items[0])


def test_an_arxiv_mega_category_is_held_to_new_papers_and_a_cap(monkeypatch):
    """cs.AI alone announces ~127 papers a day; uncapped, the three AI
    categories would roughly double score.py's daily bill."""
    import ingest

    def item(n: int, kind: str) -> bytes:
        return (f"<item><title>Paper {n}</title><link>https://arxiv.org/abs/{n}"
                f"</link><arxiv:announce_type>{kind}</arxiv:announce_type>"
                f"</item>").encode()

    class Resp:
        status_code = 200
        content = (b'<rss xmlns:arxiv="http://arxiv.org/schemas/atom">'
                   b"<channel>" + item(1, "cross") + item(2, "new")
                   + item(3, "replace") + item(4, "new") + item(5, "new")
                   + b"</channel></rss>")

    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(ingest, "pace_host", lambda url: None)
    items, _ = ingest.fetch_feed({"name": "arXiv AI", "url": "https://x",
                                  "new_only": True, "max_items": 2})
    assert [i["title"] for i in items] == ["Paper 2", "Paper 4"]


def test_hugging_face_daily_papers_arrive_as_arxiv_rows(monkeypatch):
    """2026-10-09: the only RSS of this list (papers.takara.ai) linked its
    own pages, which PREPRINT_HOSTS does not know, so a preprint would have
    reached a slide without its flag. The row must carry the arXiv link."""
    import json
    from datetime import datetime, timezone

    import ingest

    today = datetime.now(timezone.utc).isoformat()
    papers = [
        {"paper": {"id": "2610.11169", "title": "Voted", "upvotes": 40,
                   "summary": "An abstract.", "publishedAt": today,
                   "githubRepo": "https://github.com/a/b"}},
        {"paper": {"id": "2610.10001", "title": "Not yet", "upvotes": 3,
                   "summary": "Another.", "publishedAt": today}},
    ]

    class Resp:
        status_code = 200
        content = json.dumps(papers).encode()

    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(ingest, "pace_host", lambda url: None)
    items, error = ingest.fetch_feed({"name": "HF", "url": "https://x",
                                      "kind": "hf_daily_papers",
                                      "min_upvotes": 10})
    assert error is None
    assert [i["url"] for i in items] == ["https://arxiv.org/abs/2610.11169"]
    # First in the summary, so draft.links_code() finds it within 500 chars.
    assert items[0]["summary"].startswith("Code: https://github.com/a/b")


def test_a_trailing_backslash_is_not_part_of_a_url():
    """2026-10-07: a Hacker News row arrived as mistral.ai/news/mistral-
    large-4/\\ and 404'd, so Mistral's own announcement could not be read."""
    import verify_feeds
    assert verify_feeds.url_key("https://mistral.ai/news/mistral-large-4/\\") \
        == verify_feeds.url_key("https://mistral.ai/news/mistral-large-4")
