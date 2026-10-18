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
