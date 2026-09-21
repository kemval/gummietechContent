"""
proof.py — the measurements the gate is built on.

These numbers decide whether a post reaches Telegram with a button, so the
thresholds in CLAUDE.md are asserted here rather than left to the comments.
"""
from __future__ import annotations

import pytest

import proof
import render

INK = "rgb(59, 44, 35)"          # --ink  #3B2C23
CREAM = "rgb(247, 239, 226)"     # --cream #F7EFE2
PINK = "rgb(238, 110, 192)"      # --pink  #EE6EC0


def box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


# ------------------------------------------------------------------- contrast

def test_identical_colours_have_no_contrast():
    assert proof.contrast(INK, INK) == pytest.approx(1.0)


def test_contrast_is_symmetric():
    assert proof.contrast(INK, CREAM) == pytest.approx(proof.contrast(CREAM, INK))


def test_ink_on_cream_clears_the_bar_the_slides_are_held_to():
    assert proof.contrast(INK, CREAM) >= proof.MIN_CONTRAST


def test_chrome_opacity_is_a_real_contrast_reduction():
    """--ink at 0.75 over a field is not --ink. The .domain and .wordmark
    rules are held to MIN_CHROME_CONTRAST for exactly this reason."""
    full = proof.contrast(INK, PINK)
    faded = proof.contrast(INK, PINK, alpha=0.75)
    assert faded < full
    assert proof.MIN_CHROME_CONTRAST <= faded < proof.MIN_CONTRAST


def test_rgba_is_read_like_rgb():
    assert proof.channels("rgba(59, 44, 35, 0.5)") == (59.0, 44.0, 35.0)


# ------------------------------------------------------------------- geometry

def test_separated_boxes_report_their_clearance():
    assert proof.gap(box(0, 0, 10, 10), box(30, 0, 10, 10)) == 20


def test_overlapping_boxes_report_the_shallower_overlap():
    """The direction you would have to move them to part them."""
    assert proof.gap(box(0, 0, 100, 100), box(90, 10, 100, 100)) == -10


def test_touching_boxes_are_not_overlapping():
    assert proof.gap(box(0, 0, 10, 10), box(10, 0, 10, 10)) == 0


def test_a_box_inside_the_frame_has_not_escaped():
    assert proof.escape(box(50, 50, 100, 100), box(34, 34, 1012, 1282)) < 0


@pytest.mark.parametrize("child,side", [
    (box(20, 50, 100, 100), "left"),
    (box(50, 20, 100, 100), "top"),
    (box(1000, 50, 100, 100), "right"),
    (box(50, 1250, 100, 100), "bottom"),
])
def test_a_box_crossing_any_edge_is_caught(child, side):
    assert proof.escape(child, box(34, 34, 1012, 1282)) > 0, side


# -------------------------------------------------------- the locked palette

@pytest.mark.parametrize("name", sorted({h for pair in render.COLORWAYS.values()
                                         for h in pair}))
def test_every_field_hue_clears_4_5_to_1_against_ink(name):
    """CLAUDE.md's colorway invariant, asserted rather than trusted: a new
    lead or support hue must clear 4.5:1 against --ink."""
    hues = {"pink": PINK, "olive": "rgb(178, 188, 95)",
            "blush": "rgb(249, 168, 212)", "sky": "rgb(127, 178, 229)",
            "amber": "rgb(242, 180, 65)"}
    assert proof.contrast(INK, hues[name]) >= proof.MIN_CONTRAST


# --------------------------------------------- the rhythm, as proof sees it

def slide(field, n):
    return {"field": field, "id": f"slide-{n}", "els": [], "inner": {},
            "overflow": 0}


def fields_to_slides(fields):
    return [slide(f, n) for n, f in enumerate(fields, start=1)]


def test_a_correct_drop_rhythm_passes():
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(render.rhythm("pink", "olive", 5)),
                       "pink", "olive", True, report)
    assert report.verdict == "PASS"


def test_a_breakdown_that_moved_its_catch_for_a_recap_passes():
    """Where the catch falls is the format's business, so proof locates the
    dark slide rather than assuming slide 4."""
    report = proof.Report()
    proof.check_rhythm(
        fields_to_slides(render.rhythm("pink", "olive", 9, catch=7)),
        "pink", "olive", True, report)
    assert report.verdict == "PASS"


def test_two_dark_slides_are_a_block():
    """The catch is the one slide that drops to ink, in every format."""
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(
        ["pink", "cream", "dark", "olive", "dark", "pink"]),
        "pink", "olive", True, report)
    assert report.verdict == "BLOCK"


def test_no_dark_slide_at_all_is_a_block():
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(
        ["pink", "cream", "olive", "pink", "pink"]), "pink", "olive", True,
        report)
    assert report.verdict == "BLOCK"


def test_a_missing_cream_rest_slide_is_a_block():
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(
        ["pink", "olive", "pink", "dark", "pink"]), "pink", "olive", True,
        report)
    assert report.verdict == "BLOCK"


def test_bookends_that_stop_matching_are_a_block():
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(
        ["pink", "cream", "olive", "dark", "olive"]), "pink", "olive", True,
        report)
    assert report.verdict == "BLOCK"


def test_a_format_with_no_catch_must_have_no_dark_slide():
    """A Signal's dark slide would be a caveat about one of five items that
    the post does not make."""
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(render.rhythm("pink", "olive", 7, 0)),
                       "pink", "olive", False, report)
    assert report.verdict == "PASS"


def test_a_dark_slide_in_a_format_that_has_no_catch_is_a_block():
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(
        ["pink", "cream", "olive", "dark", "olive", "pink"]),
        "pink", "olive", False, report)
    assert report.verdict == "BLOCK"


def test_a_format_with_a_catch_and_no_dark_slide_is_a_block():
    report = proof.Report()
    proof.check_rhythm(fields_to_slides(
        ["pink", "cream", "olive", "pink", "olive"]),
        "pink", "olive", True, report)
    assert report.verdict == "BLOCK"


# ------------------------------------------------- the field the post lands on

def test_a_second_post_in_the_same_field_is_a_fix(posts_dir, monkeypatch):
    """render.py already says this, to a run log nobody reads at the gate.
    This report is carried into the Telegram message, which is the last place
    the rule can still be acted on — after approval the post is on the grid."""
    directory, write = posts_dir
    monkeypatch.setattr(render, "POSTS_DIR", directory)
    write("2026-09-18-first.json", colorway="ember")
    later = write("2026-09-19-second.json", colorway="ember")

    report = proof.Report()
    proof.check_colorway(later, "ember", report)
    assert report.verdict == "FIX"
    assert f"--colorway {render.vary('ember', 'ember')}" in report.render()


def test_a_free_field_is_not_a_fix(posts_dir, monkeypatch):
    directory, write = posts_dir
    monkeypatch.setattr(render, "POSTS_DIR", directory)
    write("2026-09-18-first.json", colorway="ember")
    later = write("2026-09-19-second.json", colorway="orbit")

    report = proof.Report()
    proof.check_colorway(later, "orbit", report)
    assert report.verdict == "PASS"


def test_a_post_with_no_path_is_not_checked_for_its_neighbour():
    """proof(post, colorway) without a path is still a valid call — the
    check is skipped rather than guessing which file the record came from."""
    report = proof.Report()
    proof.check_colorway(None, "ember", report)
    assert report.verdict == "PASS"


def test_the_era_fixtures_are_not_held_to_the_rule(posts_dir, monkeypatch):
    """They are not posts and never land. previous_colorway() treats a path
    outside post_order() as arriving at the end of the archive, which made
    proof report every fixture as clashing with the newest real draft."""
    directory, write = posts_dir
    monkeypatch.setattr(render, "POSTS_DIR", directory)
    write("2026-09-19-real.json", colorway="orbit")
    fixture = write("era-breakdown.json", colorway="orbit")

    report = proof.Report()
    proof.check_colorway(fixture, "orbit", report)
    assert report.verdict == "PASS"
