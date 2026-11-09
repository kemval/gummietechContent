"""weekly.py: the parts of Claude's weekly posts that code decides."""

from __future__ import annotations

import json
from datetime import date

import telegram as tg
import weekly


def test_the_stem_limit_is_what_a_telegram_button_carries():
    """weekly.py restates the limit (it runs before pip install), so this is
    what keeps the copy honest."""
    longest = max(len(p) for p in tg.PREFIXES)
    assert weekly.STEM_LIMIT == tg.CALLBACK_LIMIT - longest


def test_a_long_term_still_names_a_file_a_button_can_carry(tmp_path, monkeypatch):
    """2026-10-18: the first reference was named "2026-10-18-reference-" plus
    a 40-character slug, and review.yml refused its 65-byte button. A term
    behind "glossary-" overruns the same way."""
    posts = tmp_path / "posts"
    posts.mkdir()
    (posts / "2026-10-13-the-drop.json").write_text(json.dumps({
        "post_type": "drop", "hook": "H", "source_url": "https://x.org",
        "attribution": "A", "peer_reviewed": True, "published_at": "2026-10-13"}))
    monkeypatch.setattr(weekly, "REPO_ROOT", tmp_path)
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({
        "post_type": "term", "domain": "d", "colorway": "signal", "hook": "H",
        "term": "Reinforcement learning from human feedback, explained",
        "definition": "D", "example": "E", "the_catch": "C",
        "example_post": "2026-10-13-the-drop", "caption": "C?",
        "keywords": [], "hashtags": [], "alt_text": "T"}))
    assert weekly.finish("glossary", draft, date(2026, 10, 20), posts) == 0
    [written] = posts.glob("2026-10-20-*.json")
    assert len(written.stem.encode()) <= weekly.STEM_LIMIT


INCIDENT_DRAFT = {
    "post_type": "incident", "domain": "cloud", "colorway": "bloom",
    "hook": "H", "what_broke": "W",
    "timeline": ["09:14 UTC: Requests failed.", "10:02 UTC: Traffic recovered."],
    "root_cause": "R", "the_fix": "F", "the_catch": "C", "caption": "C?",
    "keywords": [], "hashtags": [], "alt_text": "T",
    # typed by the writer, and overwritten: credit is never the model's
    "attribution": "Somebody", "source_url": "https://elsewhere.example",
}

MENU = [{"url": "https://www.githubstatus.com/incidents/abc",
         "title": "Incident with Webhooks and Actions",
         "date": "2026-11-08", "publisher": "GitHub"}]


def test_a_recent_incident_carries_the_feed_entrys_credit(tmp_path, monkeypatch):
    """2026-11-09: the owner turned down Knight Capital (2012) — Sunday's
    incident should be recent. A recent pick's credit is the feed entry's,
    copied by code, like every other weekly credit."""
    posts = tmp_path / "posts"
    posts.mkdir()
    monkeypatch.setattr(weekly, "REPO_ROOT", tmp_path)
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({**INCIDENT_DRAFT, "source_pick": MENU[0]["url"]}))
    assert weekly.finish("incident", draft, date(2026, 11, 9), posts, MENU) == 0
    [written] = posts.glob("2026-11-09-incident-*.json")
    post = json.loads(written.read_text())
    assert post["source_url"] == MENU[0]["url"]
    assert post["attribution"] == ("GitHub, “Incident with Webhooks and "
                                   "Actions”, 8 Nov 2026")
    assert post["incident_report"] is True and post["peer_reviewed"] is False
    assert "source_pick" not in post


def test_an_incident_picked_from_outside_the_menu_is_refused(tmp_path):
    posts = tmp_path / "posts"
    posts.mkdir()
    post = {**INCIDENT_DRAFT, "source_pick": "https://news.example/outage"}
    assert any("source_pick" in p
               for p in weekly.problems("incident", post, posts, menu=MENU))


def test_a_status_pages_state_is_not_part_of_the_credit():
    """2026-11-09: the first recent incident was credited as Google Cloud,
    "RESOLVED: Multiple services were experiencing issues…" — the page's
    state when it was read, not the incident's title."""
    assert weekly.incident_title(
        "RESOLVED: Multiple services were experiencing issues in the "
        "europe-west2 region.") == ("Multiple services were experiencing "
                                    "issues in the europe-west2 region.")
    assert weekly.incident_title("Incident: Trouble connecting\n to Slack") == \
        "Trouble connecting to Slack"
    assert weekly.incident_title("GitHub availability report: September 2026") \
        == "GitHub availability report: September 2026"


def test_a_draft_over_the_word_budget_goes_back_to_the_writer(tmp_path):
    """2026-11-09: a 26-word root_cause (limit 25) was filed, and review.yml's
    auto-fix then refused the fact-check's fix to another field because the
    post was still over budget — the false line reached the chat."""
    posts = tmp_path / "posts"
    posts.mkdir()
    post = {**INCIDENT_DRAFT, "source_pick": MENU[0]["url"],
            "root_cause": " ".join(["word"] * 26)}
    assert any("root_cause is 26 words" in p
               for p in weekly.problems("incident", post, posts, menu=MENU))
