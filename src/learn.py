#!/usr/bin/env python3
"""
Layer 7: what the numbers say, so the weakest format can be cut.

§9 of the content system makes saves the primary measure, shares the second,
and profile visits the funnel one — and says explicitly that likes are not a
metric. §8 sets the decision this exists for: after thirty posts, cut the
weakest format and double the winner. This reads the numbers telegram.py
wrote onto each post and puts them in one table so that decision is a thing
you look at rather than a thing you remember.

Usage:
    python src/learn.py
    python src/learn.py --by colorway      # group by something else

No network, no API key, no LLM call. It reads posts/ and prints.

Two things it deliberately does not do:

  - **It does not compute a rate.** Saves per impression would be the honest
    measure, and Instagram does not hand over impressions without the
    Professional-account API that §4 rules out on cost. A ratio invented from
    the three numbers here would look rigorous and mean nothing.

  - **It does not rank on too little.** A median over two posts is noise
    wearing a number's clothes, so a group under MIN_GROUP is reported with
    its count and no verdict. §8 says thirty posts for a reason.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# From telegram.py because that is where these are written, and because it is
# the one module that reads posts/ without importing render.py — which would
# drag Playwright in for a script that only reads JSON.
from telegram import (METRICS_FIELDS, METRICS_KEY, POSTS_DIR, REPO_ROOT,
                      read_post)

import series

# Below this a median says more about which post went viral than about the
# group. Reported, not ranked.
MIN_GROUP = 3

GROUPS = ("post_type", "colorway", "domain", "weekday")

# The status-report pillar groups by different things, because different
# things vary in it. A report has no post_type, colorway or domain; what it
# has is the layout module the slide is built from — bars, pills, timeline,
# cards-4 — and the eyebrow that names its series. §8 puts the format decision
# at thirty posts, and "which module earns another ten" is exactly that
# decision one pillar down.
SERIES_GROUPS = ("module", "eyebrow", "weekday")

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")


def weekday(post: dict) -> str:
    """The day a post went live, which is the only grouping not in the JSON."""
    try:
        return WEEKDAYS[date.fromisoformat(post["published_at"]).weekday()]
    except (KeyError, TypeError, ValueError):
        return "?"


def numbers(post: dict) -> dict[str, int] | None:
    """A post's metrics, or None if it has none worth counting.

    An asked-but-unanswered post carries a metrics block holding only
    `asked_at`. That is not a zero — it is a question nobody has got to yet —
    so it is counted apart rather than dragging every median down.
    """
    block = post.get(METRICS_KEY) or {}
    got = {f: block[f] for f in METRICS_FIELDS if isinstance(block.get(f), int)}
    return got if len(got) == len(METRICS_FIELDS) else None


def load(directory: Path | None = None) -> tuple[
        list[tuple[Path, dict, dict]], int, int]:
    """(posts with numbers, published without, asked but unanswered)."""
    scored: list[tuple[Path, dict, dict]] = []
    unmeasured = 0
    unanswered = 0
    for path in sorted((directory or POSTS_DIR).glob("*.json")):
        post = read_post(path)
        if post is None or not post.get("published_at"):
            continue
        got = numbers(post)
        if got:
            scored.append((path, post, got))
        elif post.get(METRICS_KEY):
            unanswered += 1
        else:
            unmeasured += 1
    return scored, unmeasured, unanswered


def label(post: dict, by: str) -> str:
    if by == "weekday":
        return weekday(post)
    return str(post.get(by) or "—").strip().lower()


def table(scored: list[tuple[Path, dict, dict]], by: str) -> None:
    """Median per group, best first, with the thin ones held back."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for _, post, got in scored:
        groups[label(post, by)].append(got)

    rows = []
    for name, entries in groups.items():
        medians = {f: statistics.median(e[f] for e in entries)
                   for f in METRICS_FIELDS}
        rows.append((name, len(entries), medians))
    rows.sort(key=lambda r: (r[1] >= MIN_GROUP, r[2]["saves"]), reverse=True)

    head = f"  {'':<22}{'n':>4}" + "".join(
        f"{f.replace('_', ' '):>16}" for f in METRICS_FIELDS)
    print(f"\nBy {by}, median per post")
    print(head)
    for name, n, medians in rows:
        thin = "" if n >= MIN_GROUP else "   (too few to rank)"
        print(f"  {name[:22]:<22}{n:>4}"
              + "".join(f"{medians[f]:>16.0f}" for f in METRICS_FIELDS)
              + thin)


def ranking(scored: list[tuple[Path, dict, dict]]) -> None:
    print("\nEvery measured post, most saved first")
    print(f"  {'saves':>7}{'shares':>8}{'visits':>8}  {'published':<12}post")
    for path, post, got in sorted(scored, key=lambda s: s[2]["saves"],
                                  reverse=True):
        hook = str(post.get("hook") or post.get("title") or "").strip()
        print(f"  {got['saves']:>7}{got['shares']:>8}"
              f"{got['profile_visits']:>8}  {post['published_at']:<12}"
              f"{hook[:52]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--by", action="append", default=None, metavar="FIELD",
                    help=f"group by one of {', '.join(GROUPS)} — or, with "
                         f"--series, {', '.join(SERIES_GROUPS)}. Repeatable; "
                         f"defaults to all of them.")
    ap.add_argument("--series", action="store_true",
                    help="report on the status-report pillar in "
                         "series/reports/ instead of the carousels in posts/")
    args = ap.parse_args()

    groups = SERIES_GROUPS if args.series else GROUPS
    if args.by and set(args.by) - set(groups):
        bad = ", ".join(sorted(set(args.by) - set(groups)))
        sys.exit(f"Cannot group by {bad} here. "
                 f"{'A status report' if args.series else 'A carousel'} has "
                 f"{', '.join(groups)}.")

    scored, unmeasured, unanswered = load(
        series.REPORTS_DIR if args.series else None)
    total = len(scored) + unmeasured + unanswered
    which = "status reports" if args.series else "carousels"
    print(f"gummietech · what the numbers say · {which}")
    print(f"{total} published · {len(scored)} measured"
          + (f" · {unanswered} asked, not answered" if unanswered else "")
          + (f" · {unmeasured} not yet asked" if unmeasured else ""))

    if not scored:
        print("\nNothing measured yet. telegram.py asks for a post's numbers "
              f"three days after it goes live; reply to that message in the "
              f"chat and they land here.")
        return 0

    for by in (args.by or groups):
        table(scored, by)
    ranking(scored)

    if len(scored) < 30:
        # §8's decision point, stated rather than implied: a format cut on
        # eight posts is a coin toss with a table attached.
        print(f"\n{len(scored)} measured. §8 puts the "
              f"cut-the-weakest-format decision at 30 — read this as a "
              f"direction, not a verdict, until then.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
