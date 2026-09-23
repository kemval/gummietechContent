#!/usr/bin/env python3
"""
The status-report series: what is queued, what went out, and in what order.

The second content pillar — single 1080x1350 slides of relatable-dev humour
under a `STATUS REPORT #NN` eyebrow, posted daily. It is not a carousel
format and never will be: formats.RECORD requires `attribution`,
`source_url` and `peer_reviewed` on every record and render.load_post()
refuses one without them, because a science post that cannot name its source
must not ship. A status report has no source to name. So it gets its own
small manifest here rather than a `post_type` in formats.py.

The slides themselves are designed on a Claude Design canvas and exported to
`series/images/` by hand — nothing in src/ renders them. This module only
answers which one is next and what to say with it.

Its own module, standard library only, for the reason formats.py and
llm_errors.py are: telegram.py imports it, and telegram.py runs on
publish.yml's poll under `requests` and `python-dotenv` alone. Adding a
dependency here kills `confirm` at module load on every poll — which is
exactly what happened the day that install list fell behind telegram.py's
imports. Importing this costs nothing.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = REPO_ROOT / "series"
REPORTS_DIR = SERIES_DIR / "reports"
IMAGES_DIR = SERIES_DIR / "images"

# What a record must carry to be sendable at all: the three the message is
# made of. Two fields are deliberately absent. `module` only feeds learn.py's
# grouping, so a report without one still posts. And `number` is optional
# because the unnumbered prototypes — LIVE FEED, SELF AUDIT, HOUSE RULES,
# BEHIND THE SCENES — are real posts that carry an eyebrow instead of a
# number; order_key() is what puts them after the numbered run.
REQUIRED = ("title", "image", "caption")

# Written when the bot shows you the report; `published_at` is written when
# you tap to say it reached Instagram. Two different facts, and the gate in
# series.yml needs the first one: sending writes nothing else, so unlike
# daily.yml — which asks whether posts/ already holds a file dated today —
# this pillar has no filename to test and needs a field instead.
SENT_KEY = "sent_at"


def read_report(path: Path) -> dict | None:
    """A report record, or None having said why it could not be read."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  warning: {path.name} is unreadable ({exc}) — left alone")
        return None


def write_report(path: Path, report: dict) -> None:
    """Write a report back in the shape it was seeded in."""
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


def order_key(path: Path, report: dict) -> tuple[float, str]:
    """Posting order: by `number`, then by name.

    A record with no usable number sorts last rather than crashing the queue
    — the unnumbered prototypes (LIVE FEED, SELF AUDIT, HOUSE RULES, BEHIND
    THE SCENES) are real posts with no place in the numbering, and they go
    out after the numbered run.
    """
    try:
        return (float(report.get("number")), path.name)   # type: ignore[arg-type]
    except (TypeError, ValueError):
        return (float("inf"), path.name)


def reports() -> list[tuple[Path, dict]]:
    """Every readable report, in the order they go out."""
    found = []
    for path in sorted(REPORTS_DIR.glob("*.json")):
        report = read_report(path)
        if report is not None:
            found.append((path, report))
    return sorted(found, key=lambda pair: order_key(*pair))


def missing_fields(report: dict) -> list[str]:
    """Which of REQUIRED this record does not actually have."""
    return [f for f in REQUIRED
            if report.get(f) is None or not str(report[f]).strip()]


def image_for(report: dict) -> Path:
    """Where this report's PNG belongs, whether or not it is there yet.

    The name is resolved inside IMAGES_DIR rather than joined blindly: a
    record is a file on disk, but it is also the thing a workflow feeds to an
    upload, and `../../.env` is not an image.
    """
    name = Path(str(report.get("image", ""))).name
    return IMAGES_DIR / name


def sendable(path: Path, report: dict) -> str | None:
    """Why this report cannot be sent yet, or None if it can."""
    missing = missing_fields(report)
    if missing:
        return f"{path.name} is missing {', '.join(missing)}"
    if not image_for(report).exists():
        return (f"{path.name} has no image yet — export "
                f"{image_for(report).name} from the canvas into "
                f"{IMAGES_DIR.relative_to(REPO_ROOT)}/")
    return None


def next_unsent() -> tuple[Path, dict] | None:
    """The next report due, sent or not — the first without `sent_at`.

    It stops at that report whether or not it is ready, rather than skipping
    to the next one that is. The numbering is public: a reader meets these in
    order and a gap reads as posts gone missing, so sending #10 because #07
    has not been exported would break the one thing the sequence promises.
    Whether it can actually go out is sendable()'s answer, not this one's.
    """
    for path, report in reports():
        if not str(report.get(SENT_KEY, "")).strip():
            return path, report
    return None


def report_for_stem(stem: str) -> Path | None:
    """The report a stem names, or None.

    The stem arrives from the network — it rides in callback_data and in the
    metrics question — so anything carrying a separator is not a filename.
    Silent, unlike telegram.locate: this is the second place a stem is
    looked for, and a stem that names a post is not an error here.
    """
    if "/" in stem or "\\" in stem or stem in ("", ".", ".."):
        return None
    path = REPORTS_DIR / f"{stem}.json"
    return path if path.exists() else None


def caption_text(report: dict) -> str:
    """The Instagram caption, hashtags and all, ready to copy out of the chat.

    One blank line between the two, which is how it is pasted: Instagram
    treats the tags as part of the caption but they read as a separate block,
    and a caption that arrives pre-formatted is one less thing to fix on a
    phone at 7am.
    """
    caption = str(report.get("caption", "")).strip()
    tags = [str(t).strip() for t in report.get("hashtags") or [] if str(t).strip()]
    return f"{caption}\n\n{' '.join(tags)}".strip() if tags else caption


def label(report: dict) -> str:
    """How a report names itself in a log line or a chat message."""
    number = report.get("number")
    eyebrow = str(report.get("eyebrow") or "status report").strip()
    title = str(report.get("title") or "").strip()
    head = f"{eyebrow} #{int(number):02d}" if isinstance(number, int) else eyebrow
    return f"{head} — {title}" if title else head


# ------------------------------------------------------------ the manifest
#
# Everything below is `python src/series.py`: what is queued, what went out,
# and in what order — the question this module's docstring has always claimed
# to answer, asked out loud. It reads and prints and nothing else, and exits 0
# whatever it finds, for learn.py's reason: a report is not a gate. The gate
# is sendable(), and series.yml is what asks it.


def claimed_numbers(found: list[tuple[Path, dict]]) -> list[int]:
    """Every number the queue claims, in the order the records send."""
    return [r["number"] for _, r in found if isinstance(r.get("number"), int)]


def missing_numbers(found: list[tuple[Path, dict]]) -> list[int]:
    """The holes in the numbered run.

    The sequence is public — a follower reads it as an ongoing log, so a
    number nothing claims reads as posts gone missing rather than as a report
    nobody built. It has happened once: the finished slides ran 02-06 and then
    10-13, and #07, #08 and #09 were built afterwards to close the hole.

    Counted between the lowest and highest number still in the queue. Numbers
    below that are posted and gone, not missing, and there is nothing to say
    about numbers nobody has thought of yet.
    """
    claimed = set(claimed_numbers(found))
    if not claimed:
        return []
    return [n for n in range(min(claimed), max(claimed) + 1)
            if n not in claimed]


def duplicate_numbers(found: list[tuple[Path, dict]]) -> list[int]:
    """Numbers claimed by more than one record.

    order_key() breaks that tie on the filename, silently, so two records
    claiming #07 would send in alphabetical order and the same number would
    go out on two different days.
    """
    seen: set[int] = set()
    twice: list[int] = []
    for number in claimed_numbers(found):
        if number in seen and number not in twice:
            twice.append(number)
        seen.add(number)
    return twice


def module_runs(found: list[tuple[Path, dict]]) -> list[tuple[str, list[Path]]]:
    """Neighbouring reports built from the same layout module.

    render.vary() one pillar down. Two carousels in the same field read as one
    post in the grid; two reports in the same module read the same way, and
    the numbering already gets bent to avoid it — the commit-times timeline
    was numbered #09 rather than #08 to put three days and two other modules
    between it and #06's. That is a rule worth printing rather than
    rediscovering, so it is reported here. It is not enforced anywhere: a
    repeated layout is cosmetic, and withholding a send over one would teach
    exactly the reflex the gate depends on nobody having.
    """
    runs: list[tuple[str, list[Path]]] = []
    for path, report in found:
        module = str(report.get("module") or "").strip()
        if module and runs and runs[-1][0] == module:
            runs[-1][1].append(path)
        else:
            runs.append((module, [path]))
    return [run for run in runs if len(run[1]) > 1]


def runway(found: list[tuple[Path, dict]]) -> tuple[int, str | None]:
    """How many days of sending are in hand, and what ends them.

    Counted by walking the queue from the front rather than by counting
    records that happen to have an image, because next_unsent() stops at the
    next report whether or not it is ready: skipping ahead is the one thing
    the numbering promises not to do. So the first report that cannot be sent
    is where the runway ends, and anything exported behind it does not count
    until that one is.
    """
    days = 0
    for path, report in found:
        if str(report.get(SENT_KEY, "")).strip():
            continue
        reason = sendable(path, report)
        if reason:
            return days, reason
        days += 1
    return days, None


def today() -> date:
    """Today in the zone the account posts from, if it can be asked.

    publish_date() lives in telegram.py and is imported rather than copied,
    because two answers to "what day is it here" is how a gate and a stamp
    come to disagree. The import is inside the function deliberately:
    telegram.py imports *this* module, and it runs on publish.yml's poll under
    requests and python-dotenv alone — importing it back at module level would
    be a cycle on every poll and a dependency this module has always refused.
    A machine without requests still gets the manifest, one day-boundary less
    sure of itself.
    """
    try:
        from telegram import publish_date
        return date.fromisoformat(publish_date())
    except (ImportError, ValueError):
        return date.today()


def status(path: Path, report: dict, nxt: Path | None) -> str:
    """The one thing worth saying about this record on its line."""
    if str(report.get("published_at", "")).strip():
        return f"posted {report['published_at']}"
    if str(report.get(SENT_KEY, "")).strip():
        return f"sent {report[SENT_KEY]}"
    if not image_for(report).exists():
        return "no image"
    return "next" if path == nxt else ""


def main() -> int:
    found = reports()
    where = REPORTS_DIR.relative_to(REPO_ROOT)
    if not found:
        print("gummietech · the status-report pillar")
        print(f"\nNo reports in {where}/. A report is a JSON record there "
              f"plus its PNG in {IMAGES_DIR.relative_to(REPO_ROOT)}/ — "
              f"see docs/gummietech_status_reports.md.")
        return 0

    numbered = claimed_numbers(found)
    nxt = next_unsent()
    nxt_path = nxt[0] if nxt else None

    print(f"gummietech · the status-report pillar · {where}/")
    print(f"{len(found)} reports · {len(numbered)} numbered, "
          f"{len(found) - len(numbered)} carrying an eyebrow instead")
    print()

    for path, report in found:
        number = report.get("number")
        head = f"#{int(number):02d}" if isinstance(number, int) else "—"
        eyebrow = str(report.get("eyebrow") or "").strip()
        tail = eyebrow if eyebrow and eyebrow != "status report" else ""
        print(f"  {head:>3}  {str(report.get('module') or '?'):<12}"
              f"{str(report.get('title') or path.stem)[:42]:<44}"
              f"{status(path, report, nxt_path):<16}{tail}".rstrip())

    sent = [r for _, r in found if str(r.get(SENT_KEY, "")).strip()]
    live = [r for _, r in found if str(r.get("published_at", "")).strip()]
    days, stopper = runway(found)

    print()
    print(f"{len(found) - len(sent)} queued · {len(sent)} sent · "
          f"{len(live)} on Instagram")

    # One a day, so the runway is a count of days and a date. Dated from the
    # first send rather than from today: series.yml sends today if nothing has
    # gone out today, and tomorrow if something has.
    if days:
        now = today()
        sent_today = any(str(r.get(SENT_KEY, "")).strip() == now.isoformat()
                         for r in sent)
        first = now + timedelta(days=1 if sent_today else 0)
        last = first + timedelta(days=days - 1)
        print(f"runway: {days} day{'s' if days != 1 else ''} in hand — "
              f"{first.isoformat()} through {last.isoformat()}, one a day")
    if stopper:
        print(f"        then it stops: {stopper}")

    holes, twice = missing_numbers(found), duplicate_numbers(found)
    if numbered:
        span = f"#{min(numbered):02d}–#{max(numbered):02d}"
        gaps = (f"missing {', '.join('#%02d' % n for n in holes)}"
                if holes else "no gaps")
        dupes = (f" · #{', #'.join('%02d' % n for n in twice)} claimed twice"
                 if twice else "")
        print(f"\n  numbering  {span} · {gaps}{dupes}")

    for module, paths in module_runs(found):
        print(f"  modules    {len(paths)} in a row on {module}: "
              f"{paths[0].stem} → {paths[-1].stem}")

    if nxt:
        reason = sendable(*nxt)
        print(f"  next       {nxt[0].name} · {reason or 'ready to send'}")
    else:
        print(f"  next       nothing left unsent — "
              f"#{max(numbered) + 1:02d} onward is new work")
    return 0


if __name__ == "__main__":
    sys.exit(main())
