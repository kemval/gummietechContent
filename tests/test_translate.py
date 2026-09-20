"""
translate.py — whether a post's Spanish still matches its English.

The archive is a permalink, so stale machine-written Spanish there is the
same credibility risk as an unlabelled preprint.
"""
from __future__ import annotations

import formats
import translate


def post(**over):
    base = {"domain": "astronomy", "hook": "A hook.",
            "what_happened": "What happened.", "why_it_matters": "Why.",
            "the_catch": "The catch."}
    return base | over


def translated(record, **over):
    es = {f: f"es-{f}" for f in formats.es_fields(record)}
    es[translate.SOURCE_KEY] = translate.fingerprint(record)
    return record | {"es": es | over}


def test_the_fingerprint_is_stable():
    assert translate.fingerprint(post()) == translate.fingerprint(post())


def test_the_fingerprint_follows_the_english():
    assert translate.fingerprint(post()) != translate.fingerprint(
        post(hook="A different hook."))


def test_a_field_the_page_does_not_render_does_not_move_it():
    """Only ES_FIELDS are translated, so only they can make one stale."""
    assert translate.fingerprint(post()) == translate.fingerprint(
        post(caption="Anything at all."))


def test_a_post_with_no_spanish_needs_translating():
    assert translate.stale_reason(post()) == "no Spanish yet"


def test_an_incomplete_block_is_dropped_whole():
    """A reader who gets a Spanish hook over an English catch cannot tell a
    missing translation from a careless one."""
    record = translated(post())
    record["es"]["the_catch"] = ""
    assert "incomplete" in translate.stale_reason(record)


def test_a_matching_stamp_is_up_to_date():
    assert translate.stale_reason(translated(post())) == ""


def test_english_corrected_after_translation_is_stale():
    record = translated(post())
    record["hook"] = "A corrected hook."
    assert translate.stale_reason(record) == \
        "the English changed after it was translated"


# ------------------------------------------------- the unverifiable fifteen

def test_an_unstamped_block_is_not_reported_as_stale():
    """Deliberate: re-translating every older post would spend a day's calls
    and overwrite Spanish a person already read at the gate."""
    record = translated(post())
    del record["es"][translate.SOURCE_KEY]
    assert translate.stale_reason(record) == ""


def test_but_it_is_reported_as_unverifiable():
    """...which is the part that was missing. `--check` used to answer
    "All 17 up to date" over fifteen posts it could not check at all."""
    record = translated(post())
    del record["es"][translate.SOURCE_KEY]
    assert translate.unstamped(record)


def test_a_stamped_block_is_not_unverifiable():
    assert not translate.unstamped(translated(post()))


def test_an_incomplete_block_is_not_counted_as_unverifiable():
    """It is already stale, and counting it twice would double-report it."""
    record = translated(post())
    record["es"]["hook"] = ""
    assert not translate.unstamped(record)


def test_check_separates_verified_from_unverifiable(posts_dir, capsys):
    directory, write = posts_dir
    write("a.json", **translated(post()))
    unstamped = translated(post(hook="Another hook."))
    del unstamped["es"][translate.SOURCE_KEY]
    write("b.json", **unstamped)

    code = translate.check(sorted(directory.glob("*.json")))
    out = capsys.readouterr().out

    assert code == 0                       # nothing is stale, so CI stays green
    assert "All 1 up to date" in out       # not "All 2"
    assert "1 post carries Spanish written before" in out
