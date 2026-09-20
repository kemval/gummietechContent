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


def test_string_scores_are_accepted():
    assert score.overall({a: "8" for a in score.AXES}) == 8.0


def test_the_threshold_matches_the_documented_one():
    """docs §2: only items scoring >= 7 surface."""
    assert score.THRESHOLD == 7.0
