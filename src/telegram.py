#!/usr/bin/env python3
"""
Deliver a rendered post to Telegram, and take the publish signal back.

This is Layer 5 with a longer arm, not a way around it. `send` puts the five
slides, caption.txt and the copy blocks in a Telegram chat with one button;
nothing reaches Instagram or the web archive until a person taps it. `confirm`
is the other half: it polls for that tap and stamps `published_at` on the post
JSON, which is the only thing that lets site.py build the post.

    python src/telegram.py send posts/2026-09-15-the-tidal-bulges.json
    python src/telegram.py confirm

`confirm` also carries Layer 7: it asks for a post's Instagram numbers once
the post has settled, and writes back the reply. See the metrics section
below for why that lives here rather than in a script of its own.

Environment:
    TELEGRAM_BOT_TOKEN   from @BotFather
    TELEGRAM_CHAT_ID     the chat to send to — send= only
    PUBLISH_TZ           IANA zone the published_at date is taken in (UTC)

Five things that are deliberate:

  - **The slides go as documents, not photos.** sendPhoto re-encodes to JPEG
    and downscales past 1280px, and the slides are flat fields of colour
    behind a 10px border — exactly what JPEG bands. A document arrives
    byte-for-byte, and Telegram still shows a tappable preview for a PNG, so
    reviewing them this way costs nothing.

  - **The post stem rides in callback_data.** That is the whole of the state
    carried between the two halves: the draft JSON is committed by the daily
    workflow before the message is sent, so `confirm` only has to be told
    which file to date.

  - **getUpdates is called without an offset.** Every tap inside Telegram's
    24-hour retention window therefore comes back on every poll, which is
    what makes `confirm` idempotent and stateless — a post that already has
    `published_at` is skipped, so re-seeing a tap changes nothing and no
    cursor has to be stored between runs.

  - **A failed answerCallbackQuery is not an error.** The poll runs on a
    cron, so by the time it sees a tap the callback id is usually past the
    seconds-long window Telegram allows a bot to answer in. The edit to the
    message is the feedback that matters, and it has no such deadline.

  - **The metrics answer is an ordinary reply, not a button.** Three numbers
    do not fit in callback_data and no keyboard can carry an arbitrary
    integer, so the question goes out as a message and the reply comes back
    as one. That is also why `confirm` now asks Telegram for `message`
    updates as well as taps.

  - **A held post gets link buttons, not working ones.** When a review holds
    the post there is no approval button, and in Actions its place is taken
    by links to the two workflows that are the way back: `fix.yml`, which
    applies the fact-check and re-reviews, and `recheck.yml`, which just runs
    the review again. Links precisely because getUpdates has no offset: a
    callback tap would replay on every poll for 24 hours and re-dispatch the
    work every quarter of an hour, burning the Claude quota whose exhaustion
    is the likeliest reason the post is held. One extra tap buys
    statelessness.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from dotenv import load_dotenv

# Standard library only, and deliberately not render.py — see formats.py for
# why the table lives in its own module and this file may not reach for the
# one that imports Playwright.
from formats import body_text, es_fields, pieces, sections

# Defined here rather than imported from render.py on purpose: `confirm` runs
# on publish.yml's poll and needs nothing but requests, and render.py imports
# playwright at module level.
REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"
OUTPUT_DIR = REPO_ROOT / "output"

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 60             # generous: sendMediaGroup uploads a whole carousel
MESSAGE_LIMIT = 4096     # Telegram's cap on one text message
CALLBACK_LIMIT = 64      # ...and on callback_data, which carries the stem
CALLBACK_PREFIX = "pub:"
# The same tap, made on a post a review held. It carries the stem exactly as
# `pub:` does and dates the post identically — the difference is that it is a
# separate button a person has to choose, and it says so in the log, in the
# reply, and in the commit publish.yml makes. See send() for why it exists.
OVERRIDE_PREFIX = "held:"

# The two workflows a held post offers links to, under .github/workflows/.
# workflow_url() says why they are links and not buttons that do the work.
#
# They answer the two reasons a post is held. recheck.yml runs the same review
# again, for when the check itself broke — an exhausted quota holds a post
# exactly like a real finding does. fix.yml applies what the fact-check asked
# for and sends the corrected post back through the same review, for when the
# finding was real. Only the second is about the fact-check specifically, so
# only a fact-check hold offers it.
RECHECK_WORKFLOW = "recheck.yml"
FIX_WORKFLOW = "fix.yml"
FACTCHECK_REPORT = "factcheck"

# The poll itself, offered beside every publish button as a third link.
#
# A tap cannot be answered when it is made: confirm runs on a cron, so by the
# time it sees the tap the callback id is long past the seconds Telegram gives
# a bot to answer in — see the note at the top of this file. Nothing visibly
# happens, for up to a couple of hours, and a person who cannot tell a slow
# pipeline from a broken one learns to distrust the button. The message now
# says that outright, and this link is the way out of the wait: publish.yml
# takes a plain workflow_dispatch, so running it is two taps from the chat and
# the tap is picked up in under a minute. Idempotent like every other poll —
# running it early, or twice, or with nothing tapped, does nothing at all.
PUBLISH_WORKFLOW = "publish.yml"

SLIDE_RE = re.compile(r"^slide-(\d+)\.png$")
SIDECAR = "caption.txt"

# Telegram's cap on one sendMediaGroup. No format reaches it today — a
# Breakdown is the longest at eight — but how many slides a post has is the
# template's business, so this file does not get to assume ten is enough.
MEDIA_GROUP_LIMIT = 10

# Both checkers state their verdict on the report's first line — proof.py
# prints "PROOF · PASS", fact-check.md requires "FACT-CHECK · PASS" — and that
# line is what the gate reads. A verdict of BLOCK withholds the approval
# button, so the post cannot be marked live from the phone at all.
#
# Reading the header rather than scanning the prose is not tidiness. The first
# real fact-check to reach this gate ended "Safe to render — 0 BLOCK, 0
# required FIX" and was held by its own summary of having found nothing. A
# clean post held every day is worse than no gate: it teaches a person to tap
# the override without reading.
VERDICT_RE = re.compile(r"^(?:PROOF|FACT-CHECK) · (BLOCK|FIX|PASS)\s*$", re.M)

# A report with no verdict line has not said anything a machine can act on, so
# the words themselves still decide — which is what holds the stand-in report
# review.yml writes when a configured fact-check produced nothing. Matched
# case-sensitively and on word boundaries, so fact-check.md's own prose about
# "a block page" does not trip it, and the "not configured" stand-in, which
# deliberately contains neither word, still leaves the button in place.
GATE_RE = re.compile(r"\b(BLOCK|UNVERIFIED)\b")


class TelegramError(RuntimeError):
    """The API answered, and said no."""


def config(need_chat: bool) -> tuple[str, str]:
    # Same contract as gemini.py and ingest.py: the keys live in .env
    # locally and in the environment in CI, and load_dotenv does not
    # overwrite anything already set, so CI's secrets still win.
    load_dotenv(REPO_ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set. Create a bot by messaging "
                 "@BotFather on Telegram, then put the token in .env locally "
                 "and in the repo secrets for CI.")
    if need_chat and not chat_id:
        sys.exit("TELEGRAM_CHAT_ID is not set. Message your bot once, then "
                 "open https://api.telegram.org/bot<TOKEN>/getUpdates and "
                 "copy result[0].message.chat.id.")
    return token, chat_id


def call(token: str, method: str, payload: dict | None = None,
         files: dict | None = None, strict: bool = True) -> Any:
    """
    One Telegram API call. Returns the `result` field.

    strict=False downgrades a refusal to a warning and returns None, for the
    calls whose failure is cosmetic — see the answerCallbackQuery note above.
    """
    try:
        resp = requests.post(API.format(token=token, method=method),
                             data=payload or {}, files=files, timeout=TIMEOUT)
        body = resp.json()
    except requests.Timeout:
        raise TelegramError(
            f"{method} timed out after {TIMEOUT}s. Telegram was unreachable "
            f"or the upload was too slow — re-run the step.") from None
    except requests.RequestException as exc:
        raise TelegramError(
            f"{method} could not reach Telegram: {exc}. Check the runner's "
            f"network and re-run the step.") from None
    except ValueError:
        raise TelegramError(
            f"{method} returned {resp.status_code} with a non-JSON body: "
            f"{resp.text[:200]}") from None

    if not body.get("ok"):
        why = body.get("description", "no description")
        if not strict:
            print(f"  warning: {method} refused — {why}")
            return None
        raise TelegramError(
            f"{method} refused — {why}. If it names the token or the chat, "
            f"re-check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; if it names "
            f"a file, re-render the post.")
    return body.get("result")


def safe_cut(text: str, limit: int) -> int:
    """The largest cut at or under `limit` that does not split an &entity;.

    Callers chunk text that has already been HTML-escaped, so a blind cut can
    land inside `&amp;` and send Telegram half an entity.
    """
    amp = text.rfind("&", 0, limit)
    if amp != -1 and ";" not in text[amp:limit]:
        limit = amp
    return max(limit, 1)


def chunks(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Split on line boundaries so no message exceeds Telegram's cap."""
    out: list[str] = []
    buf = ""
    for line in text.split("\n"):
        # A single line longer than the cap cannot be split on a newline;
        # hard-cut it rather than sending something Telegram will reject.
        # Flush first: emitting a piece of this line while earlier lines are
        # still buffered would send the report out of order.
        while len(line) > limit:
            if buf:
                out.append(buf)
                buf = ""
            cut = safe_cut(line, limit)
            out.append(line[:cut])
            line = line[cut:]
        if len(buf) + len(line) + 1 > limit:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        out.append(buf)
    return out or [""]


def send_message(token: str, chat_id: str, text: str,
                 markup: dict | None = None) -> None:
    """Send text, split if long, with the keyboard on the final part."""
    parts = chunks(text)
    for i, part in enumerate(parts):
        payload = {"chat_id": chat_id, "text": part, "parse_mode": "HTML",
                   "disable_web_page_preview": "true"}
        if markup and i == len(parts) - 1:
            payload["reply_markup"] = json.dumps(markup)
        call(token, "sendMessage", payload)


def send_report(token: str, chat_id: str, name: str, body: str) -> None:
    """Send one review report as messages that are each valid HTML on their own.

    The reports are the longest and least predictable thing in the message. A
    real fact-check runs to thousands of characters where the stand-in report
    runs to two lines, which is why this never failed until the OAuth token
    started working: chunks() splits on line boundaries and knows nothing
    about markup, so a <pre> that spanned a split arrived with no closing tag
    and Telegram rejected the whole message with "Can't find end tag".

    Wrapping each chunk in its own <pre> means no tag ever crosses a boundary,
    whatever the report says or how long it runs.
    """
    e = html.escape
    # Room for the <pre></pre> wrapper and a "(2/3)" heading on its own line.
    parts = chunks(e(body), MESSAGE_LIMIT - 96)
    for i, part in enumerate(parts):
        head = f"<b>{e(name)}</b>"
        if len(parts) > 1:
            head += f" ({i + 1}/{len(parts)})"
        call(token, "sendMessage",
             {"chat_id": chat_id, "text": f"{head}\n<pre>{part}</pre>",
              "parse_mode": "HTML", "disable_web_page_preview": "true"})


def read_reviews(paths: list[Path]) -> list[tuple[str, str]]:
    """Load each review report; a missing one is a hold, not a shrug."""
    out: list[tuple[str, str]] = []
    for path in paths:
        try:
            out.append((path.stem, path.read_text().strip()))
        except OSError as exc:
            sys.exit(f"Cannot read the review at {path}: {exc}. The button is "
                     f"gated on these, so a missing report stops the send "
                     f"rather than silently sending an unreviewed post.")
    return out


def blocked_by(reviews: list[tuple[str, str]]) -> list[str]:
    """The reports that withhold the approval button.

    The verdict line wins where there is one; the last, in case a report
    quotes the format while explaining it. Without one, fall back to the
    words.
    """
    held = []
    for name, body in reviews:
        verdicts = VERDICT_RE.findall(body)
        if verdicts:
            withheld = verdicts[-1] == "BLOCK"
        else:
            withheld = bool(GATE_RE.search(body))
        if withheld:
            held.append(name)
    return held


def parse_callback(data: str) -> tuple[str, bool] | None:
    """The post stem a tapped button names, and whether it overrode a hold."""
    for prefix, overridden in ((CALLBACK_PREFIX, False),
                               (OVERRIDE_PREFIX, True)):
        if data.startswith(prefix):
            return data[len(prefix):], overridden
    return None


def workflow_url(workflow: str) -> str | None:
    """Where a held post goes to be repaired, for the link buttons.

    Assembled from the runner's own environment rather than written down, so
    it cannot rot if the repo is renamed or forked. Outside Actions both
    variables are unset and there are no links: whoever ran `send` by hand is
    already sitting at a machine that can run either workflow.
    """
    server = os.getenv("GITHUB_SERVER_URL", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not (server and repo):
        return None
    return f"{server}/{repo}/actions/workflows/{workflow}"


def waiting_note(poll: str | None) -> str:
    """What a publish tap does and does not look like, said before it is made.

    The gap this closes is not latency, it is silence. confirm answers a tap
    by editing the message, and it cannot do so until the cron next runs — so
    for up to a couple of hours the button sits there looking unhandled, which
    reads exactly like a bot that has stopped working. Saying so in advance is
    most of the fix; the link is the rest.
    """
    note = ("Nothing visible happens when you tap — nothing is listening at "
            "that moment, and that is normal. The button stays put until the "
            "next poll, usually within a couple of hours; then it disappears "
            "and a \u2705 with the date replies here. Tapping again while you "
            "wait changes nothing.")
    if poll:
        note += (" To skip the wait, tap <b>Record it now</b> after the "
                 "button above and run that poll yourself.")
    return note


def review_text(post: dict, stem: str,
                reviews: list[tuple[str, str]] | None = None,
                retry: str | None = None, fix: str | None = None,
                poll: str | None = None) -> str:
    """The copy blocks a person needs in hand to post the carousel."""
    e = html.escape
    reviews = reviews or []
    tags = " ".join(post.get("hashtags") or [])
    caption = post.get("caption", "") + (f"\n\n{tags}" if tags else "")

    flag = ("peer-reviewed" if post.get("peer_reviewed")
            else "PREPRINT — slide 4 carries the flag")
    lines = [
        f"<b>{e(stem)}</b>",
        f"<i>{e(post.get('domain', ''))} · {e(post.get('colorway') or 'signal')}"
        f" · {e(flag)}</i>",
        "",
        "<b>Caption + hashtags</b>",
        f"<pre>{e(caption)}</pre>",
        "<b>Alt text</b>",
        f"<pre>{e(post.get('alt_text', ''))}</pre>",
        "<b>Source</b>",
        e(post.get("attribution", "")),
        e(post.get("source_url", "")),
    ]

    es = post.get("es") or {}
    if es:
        # Paired with the English rather than listed alone, because this is
        # the one thing in the message that nothing has checked. proof.py
        # measures the slides and the fact-check reads the English; `es` goes
        # from a free-tier model onto a permalink with only a person in
        # between. That model coins technical terms — "semi-crystalline" came
        # back once as "semicuadráticos", which means "semi-quadratic" and is
        # not a word — and a wrong one is invisible next to nothing. The
        # English it is supposed to mirror is otherwise only in the slide
        # images further up the chat, which is not something to compare
        # against on a phone.
        lines += ["", "<b>Español — goes on the web archive</b>",
                  "<i>machine-written; you are the only thing checking it</i>"]
        # The fields come from the post's own format, so a Breakdown shows
        # its question, its mechanism steps and its limits rather than the
        # three a Drop happens to have. A field this format does not carry
        # is simply absent, not empty.
        for section in ("hook", *sections(post)):
            field = section if isinstance(section, str) else section.field
            english = (body_text(post, field) if isinstance(section, str)
                       else pieces(post, section))
            spanish = body_text(es, field)
            if not (english and spanish):
                continue
            for n, (en_piece, es_piece) in enumerate(zip(english, spanish), 1):
                label = f"{field}[{n}]" if len(english) > 1 else field
                lines += [f"<b>{e(label)}</b>",
                          f"EN {e(en_piece)}",
                          f"ES {e(es_piece)}"]

    if reviews:
        # The reports go as their own messages, just above this one — see
        # send_report() for why they cannot ride along inside this one.
        names = ", ".join(name for name, _ in reviews)
        lines += ["", f"<b>Reports above:</b> {e(names)}"]
    else:
        lines += ["", "⚠️ No review reports were passed — nothing checked "
                      "these slides or these claims."]

    held = blocked_by(reviews)
    if held:
        lines += ["", f"🛑 <b>Held by {e(', '.join(held))}.</b>"]
        # A broken check and a real finding both read as a hold, and only the
        # report says which. Each link answers one of them; both are offered
        # because from a phone the report is the only way to tell them apart.
        if retry or fix:
            what = ["No approval button."]
            if fix:
                what.append("If the report found something real, tap "
                            "<b>Apply the fixes</b> — it makes the edits it "
                            "asked for and sends the post back through the "
                            "same checks, undated.")
            if retry:
                what.append("If the check itself broke rather than the post "
                            "— an exhausted quota holds a post exactly like a "
                            "real finding does — tap <b>Re-run the "
                            "checks</b>.")
            what.append("If you have already posted this to Instagram and the "
                        "slides are right, <b>Posted anyway</b> records that, "
                        "and says in the log that it went out held.")
            what.append(waiting_note(poll))
            lines += [" ".join(what)]
        else:
            lines += [
                "No approval button. Fix the post and send it again — or, if "
                "it is already on Instagram and the slides are right, "
                "<b>Posted anyway</b> records that over the hold. "
                + waiting_note(poll)
            ]
    else:
        lines += ["", "Tap the button once it is live on Instagram. "
                      + waiting_note(poll)]
    return "\n".join(lines)


def rendered_slides(outdir: Path) -> list[Path]:
    """Every slide render.py wrote for this post, in order.

    Discovered rather than counted to five. How many slides a post has is the
    template's business — render.py finds them with querySelectorAll and a
    Breakdown has eight — and a fixed slide-1..5 list here sent the first five
    of them, reported "sent 5 slides", and left a person approving a carousel
    they had seen half of. Sorted by the number rather than the name, because
    slide-10 sorts before slide-2 as text.

    Returns [] when there are no slides, and also when the numbering has a
    hole in it: a gap is a render that stopped partway, and a partial carousel
    is exactly what must not reach the gate.
    """
    found: dict[int, Path] = {}
    for path in outdir.glob("slide-*.png"):
        match = SLIDE_RE.match(path.name)
        if match:
            found[int(match.group(1))] = path
    if sorted(found) != list(range(1, len(found) + 1)):
        return []
    return [found[i] for i in sorted(found)]


def slide_groups(slides: list[Path]) -> list[list[Path]]:
    """The slides split into media groups Telegram will accept.

    sendMediaGroup takes 2–10 items, so a format longer than ten arrives in
    more than one message. The groups are evened out instead of filled to ten
    and remaindered: eleven slides as 10 + 1 would have Telegram reject the
    second group, which takes two items at a minimum.
    """
    groups = -(-len(slides) // MEDIA_GROUP_LIMIT)
    size = -(-len(slides) // groups) if groups else 0
    return [slides[i:i + size] for i in range(0, len(slides), size)] if size else []


def send(post_path: Path, review_paths: list[Path]) -> int:
    token, chat_id = config(need_chat=True)
    stem = post_path.stem
    reviews = read_reviews(review_paths)
    held = blocked_by(reviews)

    data = CALLBACK_PREFIX + stem
    override_data = OVERRIDE_PREFIX + stem
    if max(len(data.encode()), len(override_data.encode())) > CALLBACK_LIMIT:
        sys.exit(f"The post filename is too long to carry in a Telegram "
                 f"button ({len(data.encode())} > {CALLBACK_LIMIT} bytes). "
                 f"Shorten {post_path.name} and re-render it.")

    try:
        post = json.loads(post_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Cannot read {post_path}: {exc}")

    outdir = OUTPUT_DIR / stem
    slides = rendered_slides(outdir)
    sidecar = outdir / SIDECAR
    missing = ([] if slides else ["an unbroken slide-1..N.png sequence"]) + \
              ([] if sidecar.exists() else [SIDECAR])
    if missing:
        sys.exit(f"{outdir} is missing {' and '.join(missing)}. Run "
                 f"`python src/render.py {post_path.relative_to(REPO_ROOT)}` "
                 f"first.")

    print(f"Sending {stem} to Telegram")
    try:
        # Documents, not photos — see the module docstring.
        for group in slide_groups(slides):
            with contextlib.ExitStack() as stack:
                media = [{"type": "document", "media": f"attach://{p.stem}"}
                         for p in group]
                files = {p.stem: stack.enter_context(p.open("rb"))
                         for p in group}
                call(token, "sendMediaGroup",
                     {"chat_id": chat_id, "media": json.dumps(media)}, files)
        print(f"  sent {len(slides)} slides")

        with sidecar.open("rb") as fh:
            call(token, "sendDocument", {"chat_id": chat_id}, {"document": fh})
        print(f"  sent {SIDECAR}")

        # Ahead of the summary, so the button lands on the last message.
        for name, body in reviews:
            send_report(token, chat_id, name, body)
        if reviews:
            print(f"  sent {len(reviews)} report(s)")

        # The gate is the absence of the button, not a warning next to it:
        # a held post cannot be marked published from Telegram at all.
        retry = workflow_url(RECHECK_WORKFLOW) if held else None
        # Only a fact-check hold. fix.yml applies a fact-check report and has
        # nothing to say about a layout that proof.py measured and rejected —
        # offering it there would send a person to a workflow that will read
        # the report, find nothing it can act on, and change nothing.
        fix = (workflow_url(FIX_WORKFLOW)
               if FACTCHECK_REPORT in held else None)
        # Offered on both keyboards, because both end in a tap nobody answers
        # for a couple of hours. See PUBLISH_WORKFLOW.
        poll = workflow_url(PUBLISH_WORKFLOW)
        if held:
            # A hold cannot stop the carousel reaching Instagram — that is
            # done by hand, outside this. All it can withhold is the record,
            # and a person who has already posted needs somewhere to say so
            # or the archive quietly falls out of step with the account. So
            # the normal green button stays withheld and a second, separate
            # one records the override as an override.
            rows = []
            if fix:
                rows.append([{"text": "🛠 Apply the fixes", "url": fix}])
            if retry:
                rows.append([{"text": "🔁 Re-run the checks", "url": retry}])
            rows.append([{"text": "⚠️ Posted anyway — record it",
                          "callback_data": override_data}])
            if poll:
                rows.append([{"text": "⏱ Record it now", "url": poll}])
            markup = {"inline_keyboard": rows}
            links = ", ".join(n for n, on in (("fix", fix), ("re-check", retry),
                                              ("poll", poll)) if on)
            note = (f"HELD by {', '.join(held)}, override button"
                    + (f" + {links} link(s)" if links else ""))
        else:
            rows = [[{"text": "✅ Posted to Instagram",
                      "callback_data": data}]]
            if poll:
                rows.append([{"text": "⏱ Record it now", "url": poll}])
            markup = {"inline_keyboard": rows}
            note = "button offered" + (" + poll link" if poll else "")
        send_message(token, chat_id,
                     review_text(post, stem, reviews, retry, fix, poll), markup)
        print(f"  sent the review message — {note}")
    except TelegramError as exc:
        sys.exit(str(exc))

    return 0


# ---------- metrics · Layer 7 ----------
#
# §9 of the content system makes saves and shares the primary measures and
# likes explicitly not one, and §2's Layer 7 asks for them weekly so that the
# weakest format can be cut after thirty posts. Instagram's own numbers sit
# behind a Professional-account API gated by app review, so under the $0 rule
# they are read by eye — which leaves only one real question: where does a
# person type three numbers with the least ceremony. In the chat the gate
# already lives in, on a phone that is already open.
#
# Both halves ride on machinery that exists. The question goes out from
# confirm(), which already polls on publish.yml's cron and already writes to
# posts/; the answer lands in the post JSON beside published_at, which is
# where every other fact about a post has accumulated. No sheet, no service,
# no second place to look.
#
# Idempotent against getUpdates' missing offset for the same reason
# published_at is: recording a number is a set, not an increment, so a reply
# replayed for twenty-four hours writes what is already there and changes
# nothing. When two replies disagree — someone correcting a typo — getUpdates
# returns them oldest first and the later one lands last, which is the one
# they meant.
METRICS_KEY = "metrics"
METRICS_FIELDS = ("saves", "shares", "profile_visits")
# Long enough that the numbers have stopped moving, short enough that the post
# is still recognisable in the chat when the question arrives.
METRICS_AFTER_DAYS = 3
# One question per poll, so a backlog trickles instead of arriving at once.
# There is always a backlog the first time this runs — every post already
# published is instantly due — and fifteen questions in one burst teaches a
# person to ignore the bot, which costs more than the answers are worth.
# The cron asks for a poll every fifteen minutes and the free tier delivers
# roughly one every two hours (see CLAUDE.md), so a backlog of fifteen drains
# over a day or so rather than an afternoon. Slow, but one at a time is how
# they get answered anyway.
METRICS_ASK_PER_POLL = 1
# The question carries the stem, and the reply carries it back by being a
# reply — reply_to_message.text is the rendered message, so the stem is read
# out of it rather than tracked anywhere. Telegram strips the <code> tags
# before storing that text, which is what makes this match.
METRICS_MARK = "metrics ·"
# Not anchored at the start of the line: the question opens with an emoji,
# so the mark itself is the anchor and $ closes it at the line end.
METRICS_ASK_RE = re.compile(rf"{re.escape(METRICS_MARK)} (\S+)$", re.M)
# "120 14 33", "120/14/33", "120, 14, 33" — three numbers, any separator.
# A reply that is not three numbers is ignored in silence, deliberately:
# answering it would replay that answer on every poll for a day.
METRICS_REPLY_RE = re.compile(r"^\D*(\d+)\D+(\d+)\D+(\d+)\D*$")
# The ask asks in words for a Telegram *reply*, and words were not enough:
# on 2026-09-21 nine answers arrived in one day as ordinary messages, and
# record_metrics dropped every one. reply_to_message is the only thing that
# says which post three numbers belong to — nothing else is stored — so
# three numbers typed into the chat are unattributable and lost. ForceReply
# is the platform's own mechanism for exactly this: the client opens the
# reply box already pointed at the question, so the link is made by the
# keyboard rather than by remembering to make it. A person who dismisses it
# is back where they were, which is why the sentence in the message stays.
METRICS_FORCE_REPLY = {"force_reply": True,
                       "input_field_placeholder": "saves shares visits"}


def read_post(path: Path) -> dict | None:
    """A post record, or None having said why it could not be read."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  warning: {path.name} is unreadable ({exc}) — left alone")
        return None


def write_post(path: Path, post: dict) -> None:
    """Write a post back in the shape draft.py wrote it."""
    path.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")


def post_for_stem(stem: str) -> Path | None:
    """The post a stem names, or None having said why not.

    The stem becomes a path and it arrives from the network, so anything
    carrying a separator is not a post filename.
    """
    if "/" in stem or "\\" in stem or stem in ("", ".", ".."):
        print(f"  ignored a message carrying {stem!r}")
        return None
    path = POSTS_DIR / f"{stem}.json"
    if not path.exists():
        print(f"  ignored {stem}: no such post in posts/")
        return None
    return path


def due_for_metrics(today: str) -> list[tuple[Path, dict]]:
    """Published posts old enough to have settled and never asked about."""
    due: list[tuple[Path, dict]] = []
    for path in sorted(POSTS_DIR.glob("*.json")):
        post = read_post(path)
        if post is None:
            continue
        published = str(post.get("published_at", "")).strip()
        if not published or post.get(METRICS_KEY):
            continue
        try:
            age = (date.fromisoformat(today)
                   - date.fromisoformat(published)).days
        except ValueError:
            print(f"  warning: {path.name} has published_at {published!r}, "
                  f"which is not YYYY-MM-DD — not asking about it")
            continue
        if age >= METRICS_AFTER_DAYS:
            due.append((path, post))
    return due


def ask_metrics(token: str, chat_id: str, today: str) -> int:
    """Ask for the Insights numbers on every post that has settled.

    The `metrics` block is written when the question goes out rather than when
    it is answered, because that block is also what stops the question being
    asked again on the next poll. An unanswered ask is therefore a post
    with a metrics block and no numbers in it — which learn.py reports as
    unanswered rather than as a zero, since those are very different things.
    """
    due = due_for_metrics(today)
    if not due:
        return 0
    if not chat_id:
        print(f"  {len(due)} post(s) have settled, but TELEGRAM_CHAT_ID is "
              f"not set so nothing was asked. Taps are unaffected.")
        return 0

    if len(due) > METRICS_ASK_PER_POLL:
        print(f"  {len(due)} post(s) have settled; asking about "
              f"{METRICS_ASK_PER_POLL} this poll, the rest on the next ones.")

    asked = 0
    for path, post in due[:METRICS_ASK_PER_POLL]:
        hook = str(post.get("hook", "")).strip()
        send_message(
            token, chat_id,
            f"📊 {METRICS_MARK} <code>{html.escape(path.stem)}</code>\n\n"
            f"<i>{html.escape(hook)}</i>\n"
            f"Published {html.escape(str(post['published_at']))}.\n\n"
            f"Reply to <b>this</b> message with three numbers from Instagram "
            f"Insights — <b>saves shares profile-visits</b>, like "
            f"<code>120 14 33</code>.",
            METRICS_FORCE_REPLY)
        post[METRICS_KEY] = {"asked_at": today}
        write_post(path, post)
        asked += 1
        print(f"  {path.name}: asked for its numbers")
    return asked


def record_metrics(token: str, updates: list, today: str) -> int:
    """Write back every reply that answers one of those questions."""
    recorded = 0
    for update in updates:
        message = update.get("message") or {}
        replied_to = message.get("reply_to_message") or {}
        named = METRICS_ASK_RE.search(str(replied_to.get("text", "")))
        if not named:
            continue
        numbers = METRICS_REPLY_RE.match(str(message.get("text", "")).strip())
        if not numbers:
            continue

        path = post_for_stem(named.group(1))
        if path is None:
            continue
        post = read_post(path)
        if post is None:
            continue

        values = dict(zip(METRICS_FIELDS, (int(n) for n in numbers.groups())))
        current = post.get(METRICS_KEY) or {}
        if all(current.get(field) == value for field, value in values.items()):
            continue          # the same reply, replayed — the expected case

        post[METRICS_KEY] = {**current, **values, "recorded_at": today}
        write_post(path, post)
        recorded += 1
        print(f"  {path.name}: "
              + " · ".join(f"{f.replace('_', ' ')} {v}"
                           for f, v in values.items()))

        chat = message.get("chat") or {}
        if chat.get("id") and message.get("message_id"):
            call(token, "sendMessage",
                 {"chat_id": chat["id"],
                  "reply_to_message_id": message["message_id"],
                  "text": "📊 Logged."}, strict=False)
    return recorded


def publish_date() -> str:
    """Today, in the zone the account actually posts from."""
    name = os.getenv("PUBLISH_TZ", "UTC").strip() or "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"  warning: PUBLISH_TZ={name!r} is not a zone name — dating "
              f"in UTC. Use an IANA name like America/Bogota.")
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date().isoformat()


def confirm() -> int:
    """Stamp published_at on tapped posts, and keep the metrics log up.

    Both halves read the same poll. `message` joins `callback_query` in
    allowed_updates because the Layer 7 answer is a reply typed by hand —
    see the metrics section above for why it cannot be a button.
    """
    token, chat_id = config(need_chat=False)
    try:
        updates = call(token, "getUpdates",
                       {"timeout": 0,
                        "allowed_updates": json.dumps(["callback_query",
                                                       "message"])})
    except TelegramError as exc:
        sys.exit(str(exc))

    today = publish_date()
    stamped = 0

    for update in updates or []:
        query = update.get("callback_query")
        if not query:
            continue
        parsed = parse_callback(str(query.get("data", "")))
        if parsed is None:
            continue
        stem, overridden = parsed

        path = post_for_stem(stem)
        if path is None:
            continue
        post = read_post(path)
        if post is None:
            continue

        if post.get("published_at"):
            # The expected case on every poll after the first: getUpdates
            # keeps replaying the tap for 24 hours.
            continue

        post["published_at"] = today
        write_post(path, post)
        stamped += 1
        held_note = " — over a held review" if overridden else ""
        print(f"  {path.name}: published_at = {today}{held_note}")

        call(token, "answerCallbackQuery",
             {"callback_query_id": query["id"],
              "text": f"Archiving — published_at {today}"}, strict=False)

        message = query.get("message") or {}
        if message.get("chat") and message.get("message_id"):
            # Drop the keyboard so the button cannot read as unhandled, then
            # say what happened.
            call(token, "editMessageReplyMarkup",
                 {"chat_id": message["chat"]["id"],
                  "message_id": message["message_id"]}, strict=False)
            mark = "⚠️" if overridden else "✅"
            over = (" Recorded over a held review — the reports above still "
                    "stand." if overridden else "")
            call(token, "sendMessage",
                 {"chat_id": message["chat"]["id"],
                  "reply_to_message_id": message["message_id"],
                  "text": f"{mark} {stem} — published_at {today}. "
                          f"Building the archive now.{over}"}, strict=False)

    print(f"{stamped} post(s) newly published." if stamped
          else "No new publish taps.")

    # Whether the archive has anything new to show. The caller cannot read
    # this off the diff: writing a metrics block next to published_at puts a
    # comma on that line, so it shows up as changed on a poll that published
    # nothing. Appended, never written whole — GITHUB_OUTPUT is shared with
    # every other step of the job.
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"published={'true' if stamped else 'false'}\n")

    # Recorded before asking, so a post answered in this same poll is not
    # also asked about in it.
    recorded = record_metrics(token, updates or [], today)
    asked = ask_metrics(token, chat_id, today)
    if recorded or asked:
        print(f"{recorded} post(s) got numbers, {asked} asked for theirs.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("send", help="send a rendered post for approval")
    s.add_argument("post", type=Path, help="path to the post JSON")
    s.add_argument("--review", type=Path, action="append", default=[],
                   metavar="FILE",
                   help="a fact-check or proof report to carry into the "
                        "message; any that says BLOCK withholds the button. "
                        "Repeatable.")
    sub.add_parser("confirm", help="stamp published_at on tapped posts")

    args = ap.parse_args()
    if args.command == "confirm":
        return confirm()

    post_path = args.post if args.post.is_absolute() else REPO_ROOT / args.post
    if not post_path.exists():
        sys.exit(f"No such post file: {post_path}")
    return send(post_path, args.review)


if __name__ == "__main__":
    sys.exit(main())
