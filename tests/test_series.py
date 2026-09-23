"""
The status-report pillar's numbering.

Every case here is one this repository has already got wrong once, which is
the entry criterion for the suite. The numbering is the one that bites,
because the sequence is public: a follower reads `STATUS REPORT #NN` as an
ongoing log, so a number nothing claims reads as posts gone missing, and a
number claimed twice sends the same slide number on two different days.

That is not hypothetical. The finished slides really did run 02-06 and then
10-13, and #07, #08 and #09 were built afterwards to close the hole — found
by a person counting PNGs, which is the counting this replaces.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import series


@pytest.fixture
def reports(monkeypatch, tmp_path):
    """A series/reports/ a test can fill."""
    directory = tmp_path / "reports"
    directory.mkdir()
    monkeypatch.setattr(series, "REPORTS_DIR", directory)

    def write(name: str, **record) -> Path:
        path = directory / name
        path.write_text(json.dumps(record, indent=2) + "\n")
        return path

    return write


def test_the_hole_in_the_numbered_run_is_named(reports):
    """02-06 then 10-13 — the set as it actually stood, hole and all."""
    for number in (2, 3, 4, 5, 6, 10, 11, 12, 13):
        reports(f"{number:02d}-report.json", number=number,
                title=f"report {number}", image=f"{number:02d}.png",
                caption="...")

    assert series.missing_numbers(series.reports()) == [7, 8, 9]


def test_a_number_below_the_queue_is_posted_not_missing(reports):
    """#01-#03 are on Instagram and out of the records. The run starts at the
    lowest number still queued, or every posted report would report as a hole
    forever."""
    for number in (4, 5):
        reports(f"{number:02d}-report.json", number=number, title="t",
                image=f"{number:02d}.png", caption="...")

    assert series.missing_numbers(series.reports()) == []


def test_two_records_claiming_one_number_are_reported(reports):
    """order_key() breaks that tie on the filename, silently — so without
    this the same number goes out twice, in alphabetical order, and nothing
    says so."""
    reports("07-learning-queue.json", number=7, title="learning queue",
            image="07.png", caption="...")
    reports("07-something-else.json", number=7, title="something else",
            image="07b.png", caption="...")

    assert series.duplicate_numbers(series.reports()) == [7]


def test_the_unnumbered_prototypes_are_not_holes(reports):
    """LIVE FEED, SELF AUDIT, HOUSE RULES and BEHIND THE SCENES carry an
    eyebrow instead of a number and sort last. They have no place in the run
    and must not be read as gaps in it."""
    reports("04-report.json", number=4, title="t", image="04.png",
            caption="...")
    reports("p2-tabs-open.json", eyebrow="live feed", title="tabs open",
            image="p2.png", caption="...")

    found = series.reports()
    assert series.missing_numbers(found) == []
    assert series.claimed_numbers(found) == [4]
