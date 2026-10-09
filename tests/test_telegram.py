"""
telegram.py — the gate, and the metrics that come back through it.

Two properties matter more than any single case: a report saying BLOCK must
withhold the button, and everything `confirm` writes must survive being
replayed, because getUpdates is called without an offset and every tap and
reply comes back on every poll for 24 hours.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import telegram as tg


@pytest.fixture
def posts(monkeypatch, posts_dir):
    directory, write = posts_dir
    monkeypatch.setattr(tg, "POSTS_DIR", directory)
    return write


@pytest.fixture
def quiet(monkeypatch):
    """No network. Records what would have been sent."""
    sent: list[str] = []
    monkeypatch.setattr(tg, "send_message",
                        lambda token, chat, text, markup=None: sent.append(text))
    monkeypatch.setattr(tg, "call", lambda *a, **k: None)
    return sent


def reply_update(stem: str, text: str) -> dict:
    """A reply to the bot's own metrics question, as Telegram returns it."""
    return {"message": {
        "text": text, "chat": {"id": 1}, "message_id": 9,
        "reply_to_message": {"text": f"📊 {tg.METRICS_MARK} {stem}\n\nhook"}}}


# ----------------------------------------------------------------- the gate

@pytest.mark.parametrize("body,held", [
    ("PROOF · PASS\n\nall good", False),
    ("PROOF · FIX\n\nminor", False),
    ("PROOF · BLOCK\n\noverflow", True),
    ("FACT-CHECK · BLOCK\n\nwrong author", True),
])
def test_the_verdict_line_decides(body, held):
    assert bool(tg.blocked_by([("proof", body)])) is held


def test_a_clean_report_is_not_held_by_its_own_summary():
    """The first real fact-check to reach this gate closed with "Safe to
    render — 0 BLOCK, 0 required FIX" and was held by that sentence. A clean
    post held every day teaches a person to tap the override without
    reading."""
    body = "FACT-CHECK · PASS\n\nSafe to render — 0 BLOCK, 0 required FIX"
    assert tg.blocked_by([("factcheck", body)]) == []


def test_without_a_verdict_line_the_words_still_decide():
    """What holds the stand-in review.yml writes when a configured
    fact-check produced nothing."""
    assert tg.blocked_by([("factcheck", "The step failed: UNVERIFIED.")])


def test_the_not_configured_stand_in_leaves_the_button_alone():
    """It deliberately contains neither gate word."""
    assert tg.blocked_by([("factcheck", "No token, so nothing checked this.")]) == []


def test_an_unverified_verdict_holds_even_after_a_quoted_pass():
    """An unreadable source had no verdict line of its own, so the hold
    rested on GATE_RE scanning the prose — and the last verdict line wins,
    so a report that quoted "FACT-CHECK · PASS" while explaining itself
    would have passed a post nobody could check."""
    body = ("A clean post would say:\nFACT-CHECK · PASS\n\n"
            "FACT-CHECK · UNVERIFIED\nThe source is behind a login wall.")
    assert tg.blocked_by([("factcheck", body)]) == ["factcheck"]


def test_the_last_verdict_wins_if_a_report_quotes_the_format():
    body = "A report says BLOCK, FIX or PASS on line one.\nPROOF · PASS\n"
    assert tg.blocked_by([("proof", body)]) == []


# --------------------------------------------------------------- the button

@pytest.mark.parametrize("data,expected", [
    ("pub:2026-09-15-tides", ("2026-09-15-tides", "pub:")),
    ("held:2026-09-15-tides", ("2026-09-15-tides", "held:")),
    # The third prefix exists so a status report cannot rebuild the archive —
    # see test_a_status_report_tap_does_not_rebuild_the_archive.
    ("ser:07-learning-queue", ("07-learning-queue", "ser:")),
    ("reel:2026-09-15-tides", ("2026-09-15-tides", "reel:")),
    ("something-else", None),
    ("", None),
])
def test_parse_callback(data, expected):
    assert tg.parse_callback(data) == expected


def test_the_longest_stem_draft_py_can_write_still_fits_callback_data():
    """CALLBACK_LIMIT is Telegram's 64 bytes, and the stem is the whole of
    the state carried between `send` and `confirm`. The bound is built from
    draft.py rather than written down, so shortening or lengthening a slug
    there cannot quietly overrun it here.
    """
    import draft

    # The true worst case: a headline with no separator to trim back to.
    longest = f"2026-09-18-{draft.slugify('a' * 200)}"
    assert len(longest) == 51
    for prefix in tg.PREFIXES:
        assert len(prefix + longest) <= tg.CALLBACK_LIMIT


# --------------------------------------------------------------- long text

def test_a_short_message_is_one_piece():
    assert tg.chunks("one\ntwo") == ["one\ntwo"]


def test_chunks_never_exceed_the_limit():
    text = "\n".join(f"line {i}" for i in range(2000))
    assert all(len(part) <= tg.MESSAGE_LIMIT for part in tg.chunks(text))


def test_chunking_loses_nothing_and_keeps_the_order():
    text = "\n".join(f"line {i}" for i in range(2000))
    assert "\n".join(tg.chunks(text)) == text


def test_a_single_line_longer_than_the_cap_is_hard_cut():
    parts = tg.chunks("x" * (tg.MESSAGE_LIMIT * 2 + 5))
    assert all(len(p) <= tg.MESSAGE_LIMIT for p in parts)
    assert "".join(parts) == "x" * (tg.MESSAGE_LIMIT * 2 + 5)


def test_a_cut_never_splits_an_html_entity():
    """Reports are HTML-escaped before chunking, so a blind cut can send
    Telegram half an &amp;."""
    text = "y" * (tg.MESSAGE_LIMIT - 2) + "&amp;"
    assert tg.safe_cut(text, tg.MESSAGE_LIMIT) == tg.MESSAGE_LIMIT - 2


# ----------------------------------------------------------------- metrics

def test_a_settled_post_is_due(posts):
    posts("2026-09-15-x.json", hook="h", published_at="2026-09-15")
    assert len(tg.due_for_metrics("2026-09-20")) == 1


def test_a_post_published_yesterday_is_not_due_yet(posts):
    posts("2026-09-19-x.json", hook="h", published_at="2026-09-19")
    assert tg.due_for_metrics("2026-09-20") == []


def test_an_unpublished_draft_is_never_asked_about(posts):
    posts("2026-09-15-x.json", hook="h")
    assert tg.due_for_metrics("2026-09-20") == []


def test_a_malformed_date_is_skipped_not_crashed_on(posts):
    posts("2026-09-15-x.json", hook="h", published_at="soon")
    assert tg.due_for_metrics("2026-09-20") == []


def test_asking_writes_the_block_that_stops_it_asking_again(posts, quiet):
    path = posts("2026-09-15-x.json", hook="h", published_at="2026-09-15")
    assert tg.ask_metrics("tok", "chat", "2026-09-20") == 1
    assert json.loads(path.read_text())["metrics"] == {"asked_at": "2026-09-20"}
    assert tg.ask_metrics("tok", "chat", "2026-09-20") == 0
    assert len(quiet) == 1


def test_a_backlog_trickles_rather_than_arriving_at_once(posts, quiet):
    """There is always a backlog the first time this runs — every post
    already published is instantly due — and fifteen questions in one burst
    teaches a person to ignore the bot."""
    for day in range(1, 16):
        posts(f"2026-09-{day:02d}-x.json", hook="h",
              published_at=f"2026-09-{day:02d}")
    assert tg.ask_metrics("tok", "chat", "2026-10-01") <= tg.METRICS_ASK_PER_POLL

    while tg.ask_metrics("tok", "chat", "2026-10-01"):
        pass
    assert len(quiet) == 15          # every one is asked, eventually


def test_nothing_is_asked_without_a_chat_id(posts, quiet):
    path = posts("2026-09-15-x.json", hook="h", published_at="2026-09-15")
    assert tg.ask_metrics("tok", "", "2026-09-20") == 0
    assert "metrics" not in json.loads(path.read_text())
    assert quiet == []


def test_a_reply_is_recorded(posts, quiet):
    path = posts("2026-09-15-x.json", hook="h", published_at="2026-09-15",
                 metrics={"asked_at": "2026-09-20"})
    assert tg.record_metrics("tok", [reply_update("2026-09-15-x", "120 14 33")],
                             "2026-09-20") == 1
    assert json.loads(path.read_text())["metrics"] | {} == {
        "asked_at": "2026-09-20", "saves": 120, "shares": 14,
        "profile_visits": 33, "recorded_at": "2026-09-20"}


def test_the_same_reply_replayed_writes_nothing(posts, quiet):
    """getUpdates has no offset, so this is the expected case on every poll
    for 24 hours. Recording a number is a set, not an increment."""
    posts("2026-09-15-x.json", hook="h", published_at="2026-09-15",
          metrics={"asked_at": "2026-09-20"})
    updates = [reply_update("2026-09-15-x", "120 14 33")]
    assert tg.record_metrics("tok", updates, "2026-09-20") == 1
    assert tg.record_metrics("tok", updates, "2026-09-20") == 0


def test_a_correction_wins_because_it_arrives_later(posts, quiet):
    path = posts("2026-09-15-x.json", hook="h", published_at="2026-09-15",
                 metrics={"asked_at": "2026-09-20"})
    tg.record_metrics("tok", [reply_update("2026-09-15-x", "1 2 3"),
                              reply_update("2026-09-15-x", "150 20 40")],
                      "2026-09-20")
    assert json.loads(path.read_text())["metrics"]["saves"] == 150


@pytest.mark.parametrize("text", ["150/20/40", "150, 20, 40", " 150 20 40 "])
def test_any_separator_between_the_three_numbers(posts, quiet, text):
    posts("2026-09-15-x.json", hook="h", published_at="2026-09-15",
          metrics={"asked_at": "2026-09-20"})
    assert tg.record_metrics("tok", [reply_update("2026-09-15-x", text)],
                             "2026-09-20") == 1


@pytest.mark.parametrize("update", [
    pytest.param({"message": {"text": "120 14 33", "chat": {"id": 1}}},
                 id="not a reply"),
    pytest.param({"callback_query": {"data": "pub:x", "id": "1"}},
                 id="a button tap"),
])
def test_what_is_not_an_answer_is_left_alone(posts, quiet, update):
    posts("2026-09-15-x.json", hook="h", published_at="2026-09-15",
          metrics={"asked_at": "2026-09-20"})
    assert tg.record_metrics("tok", [update], "2026-09-20") == 0


def test_a_reply_that_is_not_three_numbers_is_ignored_in_silence(posts, quiet):
    """Answering it would replay that answer on every poll for a day."""
    posts("2026-09-15-x.json", hook="h", published_at="2026-09-15",
          metrics={"asked_at": "2026-09-20"})
    assert tg.record_metrics("tok", [reply_update("2026-09-15-x", "no idea yet")],
                             "2026-09-20") == 0


@pytest.mark.parametrize("stem", ["../../etc/passwd", "a/b", "..", ""])
def test_a_stem_from_the_network_cannot_become_any_path(posts, quiet, stem):
    assert tg.record_metrics("tok", [reply_update(stem, "1 2 3")],
                             "2026-09-20") == 0
    assert tg.locate(stem) is None


def test_the_ask_carries_the_keyboard_that_makes_the_reply(posts, monkeypatch):
    """Asking in words was not enough. On 2026-09-21 nine answers arrived as
    ordinary messages and record_metrics dropped all nine, because
    reply_to_message is the only thing that says which post three numbers
    belong to. ForceReply makes the client build that link."""
    posts("2026-09-15-x.json", hook="h", published_at="2026-09-15")
    seen: list[dict | None] = []
    monkeypatch.setattr(tg, "send_message",
                        lambda token, chat, text, markup=None: seen.append(markup))
    monkeypatch.setattr(tg, "call", lambda *a, **k: None)

    tg.ask_metrics("tok", "chat", "2026-09-20")
    assert seen == [tg.METRICS_FORCE_REPLY]
    assert tg.METRICS_FORCE_REPLY["force_reply"] is True


def test_the_question_and_the_answer_agree_on_the_format(posts, quiet):
    """The ask is written in one place and read in another. When the mark
    moved behind an emoji this regex stopped matching and every reply was
    silently dropped — which is exactly what this asserts cannot happen."""
    posts("2026-09-15-x.json", hook="A hook.", published_at="2026-09-15")
    tg.ask_metrics("tok", "chat", "2026-09-20")
    asked_text = quiet[0]
    # Telegram stores the rendered text, so the <code> tags are gone by the
    # time a reply carries it back.
    rendered = asked_text.replace("<code>", "").replace("</code>", "")
    assert tg.METRICS_ASK_RE.search(rendered).group(1) == "2026-09-15-x"


# ------------------------------------------------------------- the carousel

@pytest.fixture
def rendered(tmp_path):
    """An output/<stem>/ directory holding the slides a render produced."""
    def build(*numbers: int):
        outdir = tmp_path / "out"
        outdir.mkdir(exist_ok=True)
        for n in numbers:
            (outdir / f"slide-{n}.png").write_bytes(b"\x89PNG")
        return outdir
    return build


@pytest.mark.parametrize("count", [5, 7, 8])
def test_every_slide_the_format_has_is_sent(rendered, count):
    """A fixed slide-1..5 list sent the first five slides of an eight-slide
    Breakdown and reported "sent 5 slides", so a person approved a carousel
    they had seen half of. How many slides a post has is the template's
    business — render.py discovers them, and so does this."""
    outdir = rendered(*range(1, count + 1))
    assert [p.name for p in tg.rendered_slides(outdir)] == \
        [f"slide-{i}.png" for i in range(1, count + 1)]


def test_slides_are_ordered_by_number_not_by_name(rendered):
    """slide-10.png sorts before slide-2.png as text, which would deal the
    carousel out of order."""
    outdir = rendered(*range(1, 12))
    assert [p.name for p in tg.rendered_slides(outdir)][:3] == \
        ["slide-1.png", "slide-2.png", "slide-3.png"]


@pytest.mark.parametrize("present", [(1, 2, 4, 5), (2, 3, 4), ()])
def test_a_gap_in_the_numbering_is_not_a_carousel(rendered, present):
    """A hole means a render that stopped partway. Half a post must not
    reach the gate looking whole."""
    assert tg.rendered_slides(rendered(*present)) == []


def test_other_png_files_in_the_directory_are_not_slides(rendered):
    outdir = rendered(1, 2, 3, 4)
    (outdir / "preview.png").write_bytes(b"\x89PNG")
    assert len(tg.rendered_slides(outdir)) == 4


@pytest.mark.parametrize("count,sizes", [
    (4, [4]), (8, [8]), (10, [10]), (11, [6, 5]), (20, [10, 10]),
])
def test_a_long_format_is_split_into_groups_telegram_accepts(count, sizes):
    """sendMediaGroup takes 2-10 items. Evened out rather than filled to ten
    and remaindered, because 10 + 1 would have the second group rejected."""
    groups = tg.slide_groups([Path(f"slide-{i}.png") for i in range(1, count + 1)])
    assert [len(g) for g in groups] == sizes
    assert sum(len(g) for g in groups) == count
    assert all(2 <= len(g) <= tg.MEDIA_GROUP_LIMIT for g in groups)


def test_send_uploads_the_whole_carousel(monkeypatch, tmp_path, posts_dir, quiet):
    """The bug this file is a post-mortem for lived in send(), not in a
    helper: it built its upload list from a constant, so the eight-slide
    Breakdown below went to the gate as five."""
    record = json.loads(
        (Path(__file__).resolve().parent.parent
         / "posts" / "era-breakdown.json").read_text())
    _, write = posts_dir
    post_path = write("2026-09-19-era-breakdown.json", **record)

    outdir = tmp_path / "output" / post_path.stem
    outdir.mkdir(parents=True)
    for i in range(1, 9):
        (outdir / f"slide-{i}.png").write_bytes(b"\x89PNG")
    (outdir / "caption.txt").write_text("caption")

    uploaded: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(tg, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(tg, "config", lambda need_chat=False: ("tok", "1"))
    monkeypatch.setattr(tg, "call", lambda token, method, payload, files=None:
                        uploaded.append((method, list(files or {}))))

    assert tg.send(post_path, []) == 0
    slides = [name for method, names in uploaded
              if method == "sendMediaGroup" for name in names]
    assert slides == [f"slide-{i}" for i in range(1, 9)]
    assert ("sendDocument", ["document"]) in uploaded


# --------------------------------------------------- the two pillars, one poll

@pytest.fixture
def reports(monkeypatch, tmp_path):
    """A series/reports/ a test can fill, pointed at by both modules."""
    directory = tmp_path / "reports"
    directory.mkdir()
    monkeypatch.setattr(tg.series, "REPORTS_DIR", directory)

    def write(name: str, **record) -> Path:
        path = directory / name
        path.write_text(json.dumps(record, indent=2) + "\n")
        return path

    return write


def tap_update(data: str) -> dict:
    """A button tap, as Telegram returns it."""
    return {"callback_query": {"id": "1", "data": data,
                               "message": {"chat": {"id": 1},
                                           "message_id": 9}}}


def test_a_status_report_tap_does_not_rebuild_the_archive(
        posts, reports, quiet, monkeypatch, tmp_path):
    """site.py reads posts/ and nothing else, so a status report reaching
    `published=true` would rebuild the whole archive into byte-identical HTML
    every single day it went out. Same shape as the metrics-comma bug: a write
    next to published_at claiming a publish that did not happen."""
    reports("07-learning-queue.json", title="learning queue",
            image="07.png", caption="c")
    monkeypatch.setattr(tg, "call",
                        lambda t, m, p=None, f=None, strict=True:
                        [tap_update("ser:07-learning-queue")]
                        if m == "getUpdates" else None)
    monkeypatch.setattr(tg, "config", lambda need_chat: ("tok", "1"))
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    assert tg.confirm() == 0
    assert "published=false" in out.read_text()


def test_a_carousel_tap_still_does(posts, reports, quiet, monkeypatch,
                                   tmp_path):
    """The other half of the same rule — the science pillar must be unchanged."""
    posts("2026-09-15-x.json", hook="h")
    monkeypatch.setattr(tg, "call",
                        lambda t, m, p=None, f=None, strict=True:
                        [tap_update("pub:2026-09-15-x")]
                        if m == "getUpdates" else None)
    monkeypatch.setattr(tg, "config", lambda need_chat: ("tok", "1"))
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    assert tg.confirm() == 0
    assert "published=true" in out.read_text()


def test_locate_does_not_confuse_the_two_collections(posts, reports, quiet):
    """A stem is written into a message once and comes back once. The
    era*.json and resolve-post post-mortems are both this shape: a path
    outside the expected set read as belonging to it."""
    posts("2026-09-15-x.json", hook="h")
    reports("07-learning-queue.json", title="t", image="i.png", caption="c")

    assert tg.locate("2026-09-15-x").parent.name == "posts"
    assert tg.locate("07-learning-queue").parent.name == "reports"
    assert tg.locate("nothing-of-the-sort") is None


# A swapped-out status report keeps its ✅ in the chat, and getUpdates replays
# a tap for 24 hours — past the moment the report goes out again tomorrow.
NOON_0930 = 1790769600        # 2026-09-30 12:00 UTC


@pytest.mark.parametrize("report, stale", [
    ({"sent_at": "2026-09-30"}, False),   # the live button on today's send
    ({}, True),                           # taken back, not re-sent yet
    ({"sent_at": "2026-10-01"}, True),    # re-sent since: the old message
])
def test_a_tap_on_a_swapped_out_send_records_nothing(monkeypatch, report,
                                                     stale):
    monkeypatch.setenv("PUBLISH_TZ", "UTC")
    assert tg.stale_series_tap(report, {"date": NOON_0930}) is stale


# ------------------------------------------------- swapping today's report
#
# A swap takes a report back by clearing its sent_at. The order is the whole
# point: cleared before the new one is out, a send that broke halfway would
# leave neither report as today's, and series.yml would send #10 again on
# its next firing as though nothing had gone out.

@pytest.fixture
def queue(monkeypatch, tmp_path):
    """A series/ a test can fill; every report written gets its image."""
    import series
    reports, images = tmp_path / "reports", tmp_path / "images"
    reports.mkdir()
    images.mkdir()
    monkeypatch.setattr(series, "REPORTS_DIR", reports)
    monkeypatch.setattr(series, "IMAGES_DIR", images)
    monkeypatch.setattr(series, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(tg, "config", lambda need_chat: ("tok", "1"))
    monkeypatch.setenv("PUBLISH_TZ", "UTC")

    def write(name: str, **record) -> Path:
        image = f"{Path(name).stem}.png"
        (images / image).write_bytes(b"\x89PNG")
        path = reports / name
        path.write_text(json.dumps({"title": name, "caption": ".",
                                    "image": image, **record}))
        return path

    return write


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def test_a_swap_sends_the_unnumbered_one_and_requeues_today(queue, quiet):
    today = tg.publish_date()
    numbered = queue("10-a.json", number=10, sent_at=today)
    spare = queue("p1-b.json")

    assert tg.swap_series() == 0
    assert read(spare)["sent_at"] == today
    assert "sent_at" not in read(numbered)


def test_a_swap_that_breaks_halfway_leaves_today_as_it_was(queue, monkeypatch):
    today = tg.publish_date()
    numbered = queue("10-a.json", number=10, sent_at=today)
    spare = queue("p1-b.json")

    def refuse(*a, **k):
        raise tg.TelegramError("Bad Request: chat not found")
    monkeypatch.setattr(tg, "call", refuse)
    monkeypatch.setattr(tg, "send_message", refuse)

    with pytest.raises(SystemExit):
        tg.swap_series()
    assert read(numbered)["sent_at"] == today
    assert "sent_at" not in read(spare)


def test_with_no_spare_a_swap_says_so_and_changes_nothing(queue, quiet):
    today = tg.publish_date()
    numbered = queue("10-a.json", number=10, sent_at=today)
    queue("11-b.json", number=11)

    assert tg.swap_series() == 0
    assert read(numbered)["sent_at"] == today
    assert "Nothing swapped" in quiet[-1]


@pytest.mark.parametrize("days_before, recorded", [(0, True), (1, False)])
def test_confirm_does_not_date_a_report_from_its_swapped_out_send(
        queue, posts, monkeypatch, days_before, recorded):
    """The helper is tested above; this is that confirm() actually asks it.
    Yesterday's message is the swapped-out send of a report re-sent today."""
    import time
    report = queue("10-a.json", number=10, sent_at=tg.publish_date())
    tap = {"callback_query": {
        "id": "1", "data": "ser:10-a",
        "message": {"date": int(time.time()) - days_before * 86400,
                    "chat": {"id": 1}, "message_id": 5}}}
    monkeypatch.setattr(
        tg, "call",
        lambda token, method, *a, **k: [tap] if method == "getUpdates" else None)

    tg.confirm()
    assert bool(read(report).get("published_at")) is recorded


# --------------------------------------------------- the Another story link

@pytest.fixture
def gate(monkeypatch, posts, tmp_path):
    """send() as review.yml runs it, keeping the keyboard it would send."""
    monkeypatch.setattr(tg, "config", lambda need_chat: ("tok", "1"))
    monkeypatch.setattr(tg, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(tg, "call", lambda *a, **k: None)
    keyboards: list[list[str]] = []
    monkeypatch.setattr(
        tg, "send_message",
        lambda token, chat, text, markup=None: keyboards.append(
            [b["text"] for row in (markup or {}).get("inline_keyboard", [])
             for b in row]))

    def run(post_type: str) -> list[str]:
        stem = f"2026-09-30-{post_type}"
        path = posts(f"{stem}.json", post_type=post_type, hook="h")
        outdir = tmp_path / "output" / stem
        outdir.mkdir(parents=True)
        for n in range(1, 6):
            (outdir / f"slide-{n}.png").write_bytes(b"\x89PNG")
        (outdir / tg.SIDECAR).write_text("caption")
        tg.send(path, [])
        return keyboards[-1]

    return run


@pytest.mark.parametrize("post_type, offered", [
    ("drop", True), ("signal", True),
    ("breakdown", False),      # written by hand: there is no "next one"
])
def test_another_story_is_offered_only_where_draft_py_can_write_one(
        gate, post_type, offered):
    assert ("🗑 Another story" in gate(post_type)) is offered


def test_an_empty_series_queue_is_said_in_the_chat(monkeypatch, quiet):
    """On 2026-10-06 the queue ran out and series.yml printed that to the
    Actions log only, exit 0 — the day's report just did not arrive. An empty
    queue is waiting on a person, so it has to reach the person."""
    monkeypatch.setattr(tg, "config", lambda need_chat=False: ("tok", "1"))
    assert tg.series_ran_out() == 0
    assert len(quiet) == 1 and "No status report today" in quiet[0]


def test_a_dry_run_of_an_empty_queue_sends_nothing(monkeypatch, quiet):
    monkeypatch.setattr(tg, "config", lambda need_chat=False: pytest.fail(
        "a dry run must not need credentials"))
    assert tg.series_ran_out(dry_run=True) == 0
    assert quiet == []
