"""
render.py — the rhythm, and which template a post gets.

The colour tokens and the slide rhythm are locked in CLAUDE.md. Generalising
the rhythm from five slides to any number is only safe if five still produces
exactly what it produced before, so that is asserted first and hardest.
"""
from __future__ import annotations

import pytest

import render


@pytest.mark.parametrize("name,pair", sorted(render.COLORWAYS.items()))
def test_five_slides_still_give_the_locked_drop_rhythm(name, pair):
    """lead · cream · support · dark · lead, for every family. If this moves,
    every post on the grid changes at once."""
    lead, support = pair
    assert render.rhythm(lead, support, 5) == [lead, "cream", support,
                                               "dark", lead]


@pytest.mark.parametrize("count", [4, 5, 6, 8, 9, 10])
def test_the_invariants_hold_at_every_length(count):
    fields = render.rhythm("pink", "olive", count)
    assert len(fields) == count
    assert fields[0] == fields[-1] == "pink", "the bookends share the lead"
    assert fields[1] == "cream", "slide 2 is the rest slide"
    assert fields[-2] == "dark", "the catch drops to ink"
    assert fields.count("dark") == 1, "only the catch is dark"
    assert fields.count("cream") == 1, "only the rest slide is cream"


def test_a_longer_format_only_extends_the_middle():
    """A Breakdown is a Drop with more mechanism in it, not a different
    grid."""
    short = render.rhythm("pink", "olive", 5)
    long = render.rhythm("pink", "olive", 9)
    assert long[:2] == short[:2]
    assert long[-2:] == short[-2:]


def test_a_template_too_short_to_carry_the_rhythm_is_clamped():
    """Below four there is nowhere to put the bookends, the rest slide and
    the catch. render.py refuses such a template outright; this only makes
    sure the rule itself cannot return a broken list."""
    assert len(render.rhythm("pink", "olive", 2)) == render.MIN_SLIDES


def test_an_unknown_colorway_falls_back_rather_than_failing(capsys):
    lead, fields = render.slide_fields("chartreuse")
    assert lead == render.COLORWAYS[render.DEFAULT_COLORWAY][0]
    assert "chartreuse" in capsys.readouterr().out


def test_no_colorway_at_all_is_silent():
    """era.json predates the field; a missing one is not a mistake to report."""
    render.slide_fields(None)
    assert render.slide_fields(None)[0] == \
        render.COLORWAYS[render.DEFAULT_COLORWAY][0]


# ------------------------------------------------------------- the template

def test_a_drop_gets_the_drop_template():
    assert render.template_for("drop") == "drop.html"


def test_an_unknown_type_falls_back_with_a_warning(capsys):
    assert render.template_for("explainer") == "drop.html"
    out = capsys.readouterr().out
    assert "explainer" in out and "drop" in out


@pytest.mark.parametrize("post_type", ["../../etc/passwd", "drop/../x", "..",
                                       "dr op", "breakdown.html"])
def test_post_type_cannot_become_any_path(post_type):
    """post_type comes from the model. It is only ever a key in FORMATS, so
    nothing it contains can reach the filesystem — the template name comes
    from the table, never from the string."""
    assert render.template_for(post_type) == "drop.html"


def test_the_type_lookup_is_case_and_space_insensitive():
    assert render.template_for("  Breakdown ") == "breakdown.html"


def test_a_missing_type_is_silent(capsys):
    assert render.template_for(None) == "drop.html"
    assert capsys.readouterr().out == ""


def test_every_format_in_the_table_has_its_template_on_disk():
    """The table names the file; nothing checks at render time, so a typo
    here would be a TemplateNotFound at the gate."""
    for name, fmt in render.FORMATS.items():
        assert (render.TEMPLATE_DIR / fmt.template).is_file(), name


# ------------------------------------------------- where the catch falls

def test_the_catch_defaults_to_second_from_last():
    """A Drop ends catch then CTA, and so does a Breakdown with no recap."""
    assert render.rhythm("pink", "olive", 8)[-2] == "dark"


def test_a_format_can_move_the_catch_back_for_a_recap_slide():
    """docs §1 ends a Breakdown limits -> recap -> CTA. The limits slide is
    half of what that section calls the account's competitive advantage, so
    it is the one that goes dark either way."""
    fields = render.rhythm("pink", "olive", 9, catch=7)
    assert fields[6] == "dark"
    assert fields.count("dark") == 1


@pytest.mark.parametrize("count", [5, 8, 9, 10])
@pytest.mark.parametrize("offset", [1, 2])
def test_no_two_neighbouring_slides_ever_share_a_field(count, offset):
    """A counter put lead next to the final lead whenever the middle came
    out an odd length, which reads as a duplicated slide rather than a
    beat."""
    fields = render.rhythm("pink", "olive", count, catch=count - offset)
    assert all(a != b for a, b in zip(fields, fields[1:])), fields


@pytest.mark.parametrize("asked", [1, 2, 99, -3])
def test_an_impossible_catch_position_is_clamped_not_honoured(asked):
    """Slide 1 is the hook, slide 2 the rest slide and the last is the CTA;
    none of them can be the catch."""
    fields = render.rhythm("pink", "olive", 9, catch=asked)
    assert fields.count("dark") == 1
    assert fields[0] != "dark" and fields[1] != "dark" and fields[-1] != "dark"


def test_catch_zero_means_the_format_has_none():
    """A Signal. The dark slide is where a post's caveat goes, and a roundup
    of five sources has five of them or none."""
    assert "dark" not in render.rhythm("pink", "olive", 7, catch=0)


# ------------------------------------------------------- formats

def test_a_drop_and_a_breakdown_need_different_fields():
    drop = render.required({"post_type": "drop"})
    breakdown = render.required({"post_type": "breakdown"})
    assert "what_happened" in drop and "what_happened" not in breakdown
    assert "mechanism" in breakdown and "mechanism" not in drop
    # attribution is a legal requirement, not a format's choice.
    for fields in (drop, breakdown):
        assert {"hook", "attribution", "alt_text", "source_url"} <= set(fields)


def test_a_breakdown_shares_the_two_slides_that_are_the_differentiator():
    """docs §1 calls why_it_matters and the_catch the account's entire
    competitive advantage, in both formats. Sharing the field names is what
    lets site.py, translate.py and the gate treat them identically."""
    breakdown = render.required({"post_type": "breakdown"})
    assert "why_it_matters" in breakdown and "the_catch" in breakdown


def test_an_optional_section_is_not_required_but_is_rendered_when_present():
    without = {"post_type": "breakdown"}
    with_recap = {"post_type": "breakdown", "recap": "One line."}
    assert "recap" not in render.required(without)
    assert "recap" not in [s.field for s in render.sections(without)]
    assert "recap" in [s.field for s in render.sections(with_recap)]


def test_es_fields_follow_the_format():
    assert "mechanism" in render.es_fields({"post_type": "breakdown"})
    assert "mechanism" not in render.es_fields({"post_type": "drop"})
    # domain and hook are on every page, whatever the format.
    assert render.es_fields({"post_type": "drop"})[:2] == ("domain", "hook")


def test_body_text_reads_a_list_field_one_slide_at_a_time():
    post = {"mechanism": ["Step one.", "Step two.", "  "]}
    assert render.body_text(post, "mechanism") == ["Step one.", "Step two."]


def test_body_text_reads_a_plain_field_as_one_piece():
    assert render.body_text({"the_catch": "A caveat."}, "the_catch") == \
        ["A caveat."]


def test_body_text_of_a_field_that_is_not_there():
    assert render.body_text({}, "recap") == []


def test_the_word_budget_measures_each_mechanism_step_separately():
    """docs §1's rule is per slide. Three steps measured as one string would
    pass a budget none of them meets."""
    post = {"post_type": "breakdown", "hook": "Short hook.",
            "the_question": "A question.", "the_intuition": "An intuition.",
            "mechanism": ["one " * 30, "two " * 5],
            "why_it_matters": "It matters.", "the_catch": "A limit."}
    over = [where for where, count, limit in render.word_budget(post)
            if count > limit]
    assert over == ["mechanism[1]"]


# ---------------------------------------------------------- the Signal

SIGNAL = {
    "post_type": "signal",
    "hook": "5 things you missed this week",
    "alt_text": "A roundup.",
    "items": [
        {"claim": "One thing happened.", "attribution": "A et al. (2026)",
         "source_url": "https://example.org/1", "peer_reviewed": True},
        {"claim": "Another thing happened.", "attribution": "B et al. (2026)",
         "source_url": "https://example.org/2", "peer_reviewed": False},
    ],
}


def test_a_signal_needs_no_record_level_source():
    """A roundup has five sources, not one. attribution, source_url and
    peer_reviewed move onto each item — §7.3 is not satisfied by crediting
    one of five."""
    fields = render.required(SIGNAL)
    assert "items" in fields
    for moved in ("attribution", "source_url", "peer_reviewed"):
        assert moved not in fields


def test_every_item_must_carry_its_own_credit_and_flag():
    short = {**SIGNAL, "items": [{"claim": "Only a claim."}]}
    missing = render.missing_from_entries(short)
    assert missing == ["items[1]: attribution", "items[1]: source_url",
                       "items[1]: peer_reviewed"]


def test_a_complete_signal_is_missing_nothing():
    assert render.missing_from_entries(SIGNAL) == []


def test_peer_reviewed_false_is_not_read_as_absent():
    """`False` is the whole point of the field; a truthiness test would
    report it missing and refuse to render a correctly labelled preprint."""
    assert "items[2]: peer_reviewed" not in render.missing_from_entries(SIGNAL)


def test_a_signal_needs_one_flag_per_unreviewed_item():
    """§7.2 is a per-claim rule. One of these two items is a preprint."""
    assert render.preprint_claims(SIGNAL) == 1


def test_a_single_source_format_claims_one_flag_or_none():
    assert render.preprint_claims({"post_type": "drop",
                                   "peer_reviewed": False}) == 1
    assert render.preprint_claims({"post_type": "drop",
                                   "peer_reviewed": True}) == 0


def test_only_the_claim_of_an_item_is_prose():
    """The source and the flag beside it are not translated or measured: a
    journal name is the same in both languages and a translated DOI is
    wrong."""
    section = render.sections(SIGNAL)[0]
    assert render.pieces(SIGNAL, section) == ["One thing happened.",
                                              "Another thing happened."]


def test_an_es_block_holds_the_same_section_as_plain_strings():
    es = {"items": ["Pasó una cosa.", "Pasó otra cosa."]}
    assert render.body_text(es, "items") == ["Pasó una cosa.",
                                             "Pasó otra cosa."]
