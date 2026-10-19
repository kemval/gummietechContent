"""
The newsletter's week.

Every case here is one this repository has already got wrong once, which is
the entry criterion for the suite. The Monday issue and Monday's Drop share
a day, and the window used to end on the day the issue was built: the
2026-10-05 Drop fell before the next issue's start, and the 2026-10-12 Drop
went out after its own issue was built, so neither reached a reader.
"""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta

from conftest import REPO_ROOT

# `import site` would return the standard library's site module, which
# Python loads at startup, so the archive builder is loaded by path.
_spec = importlib.util.spec_from_file_location(
    "gummie_site", REPO_ROOT / "src" / "site.py")
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)


def post(day: date) -> dict:
    return {"published": day, "slug": f"{day}-post", "hook": f"Post {day}",
            "alt_text": "", "body": [], "sources": []}


def test_consecutive_weekly_issues_cover_every_post_once():
    mondays = [date(2026, 10, 12), date(2026, 10, 19)]
    days = [date(2026, 10, 5) + timedelta(days=n) for n in range(14)]
    posts = [post(d) for d in days]
    issues = [site.newsletter(posts, monday) for monday in mondays]
    for d in days:
        found = sum(f"Post {d}<" in issue for issue in issues)
        assert found == 1, f"{d} is in {found} issues"


def test_the_issue_leaves_its_own_day_to_the_next_one():
    monday = date(2026, 10, 19)
    issue = site.newsletter([post(monday), post(monday - timedelta(days=7))],
                            monday)
    assert f"Post {monday}<" not in issue
    assert f"Post {monday - timedelta(days=7)}<" in issue
