#!/usr/bin/env python3
"""
Check every feed URL in feeds/*.yaml and report which ones are live.

Fetches with requests using a browser User-Agent, then hands the bytes to
feedparser. Publishers behind Cloudflare reject unfamiliar user agents with
403s or HTML block pages, which feedparser reports as "not well-formed" —
so the UA matters more than it should.

Usage:
    python src/verify_feeds.py
    python src/verify_feeds.py --file feeds/tier1_primary.yaml
    python src/verify_feeds.py --verbose
"""

import argparse
import sys
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_DIR = REPO_ROOT / "feeds"
TIMEOUT = 20

# A feed can answer 200 with a full item list and still be finished. Nothing
# above notices: the fetch succeeds, feedparser returns entries, and this
# file reported SemiAnalysis as OK with 10 entries on 2026-09-22 while its
# lastBuildDate said 23 Sep 2025. ingest.py would have dropped all ten on
# MAX_AGE_DAYS and taken a row from it never, and watch.py's feeds check
# asks only whether entries come back, which they do.
#
# 60 days rather than something tighter because watch.py sends this to a
# chat, and a watcher that cries wolf is one nobody reads. Measured across
# all 65 feeds on 2026-09-22, the newest-entry age of the live set ran
# median 0d, p90 5d, max 7d — while the three dead candidates that prompted
# this were 215d, 371d and 609d. Anything in between is a publication that
# has stopped or moved, not one having a quiet month.
STALE_AFTER_DAYS = 60

# A real browser UA. Feed endpoints are public, but many sit behind bot
# filters that block anything that doesn't look like a browser.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/rss+xml, application/atom+xml, application/xml, "
        "text/xml, */*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Several publishers list four feeds on one host (www.nasa.gov, for one),
# and the YAML groups them, so an unpaced pass fires them back to back and
# earns a 429 on all but the first. Space consecutive requests to the same
# host; feeds on different hosts are never delayed. Both this module and
# ingest.py fetch every feed, so both must pace.
MIN_HOST_INTERVAL = 2.0
_last_request_at: dict[str, float] = {}


def pace_host(url: str) -> None:
    """Sleep just long enough that this host is not hit twice in a row."""
    host = urlparse(url).netloc
    wait = MIN_HOST_INTERVAL - (time.monotonic() - _last_request_at.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_request_at[host] = time.monotonic()


OK = "\033[92m"
BAD = "\033[91m"
WARN = "\033[93m"
DIM = "\033[2m"
END = "\033[0m"


def load_feed_files(single_file=None):
    """Return the YAML feed lists to check."""
    if single_file:
        path = Path(single_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return [path]
    return sorted(FEEDS_DIR.glob("*.yaml"))


def all_feeds(single_file=None) -> Iterator[tuple[Path, dict]]:
    """Every feed entry in the YAML lists, paired with the file it came from.

    Its own function because main() is not the only caller any more: watch.py
    sweeps the same lists on a cron, and a second copy of the parsing is a
    second place for the `feeds:` key to be spelled wrong. A missing file is
    skipped with a warning rather than ending the sweep — one bad list must
    not hide the state of the other two.
    """
    for feed_file in load_feed_files(single_file):
        if not feed_file.exists():
            print(f"{BAD}Missing file:{END} {feed_file}")
            continue
        data = yaml.safe_load(feed_file.read_text()) or {}
        for entry in data.get("feeds", []):
            yield feed_file, entry


def newest_entry_age(parsed) -> int | None:
    """How many days since the newest dated entry, or None if undated.

    None is not a fault and must never be reported as one. Some feeds omit
    dates entirely — ingest.py keeps their entries on purpose for exactly
    that reason — so a feed with no parseable date has no age to test, the
    same way an undated row has none.

    It reads the whole entry list rather than trusting entry[0], because
    document order is the publisher's choice and several feeds here are not
    newest-first.
    """
    newest = None
    for entry in parsed.entries:
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        if not stamp:
            continue
        try:
            when = datetime(*stamp[:6], tzinfo=timezone.utc)
        except ValueError:                 # feedparser hands back odd tuples
            continue
        if newest is None or when > newest:
            newest = when
    if newest is None:
        return None
    return (datetime.now(timezone.utc) - newest).days


def check_feed(entry, verbose=False):
    """
    Fetch one feed and classify the result.

    Returns (status, detail, age) where status is 'ok', 'empty' or 'fail'
    and age is the newest entry's age in days — None when the feed is
    undated, or when it never got far enough to have entries at all.

    The age is returned rather than judged here because two callers want
    different things from it: this file prints it for a person choosing a
    feed, and watch.py compares it to STALE_AFTER_DAYS on a cron. The
    threshold lives beside that constant so there is only one of it.
    """
    url = entry.get("url", "")
    if not url:
        return "fail", "no url in entry", None

    pace_host(url)
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
    except requests.exceptions.SSLError:
        return "fail", "SSL error — check the certificate or try http://", None
    except requests.exceptions.ConnectionError:
        return "fail", "connection failed — domain may be gone", None
    except requests.exceptions.Timeout:
        return "fail", f"timed out after {TIMEOUT}s", None
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}", None

    if resp.status_code == 403:
        return "fail", "HTTP 403 — blocked. Try a different UA or use RSSHub.", None
    if resp.status_code == 404:
        return "fail", "HTTP 404 — feed moved. Check the site's /rss page.", None
    if resp.status_code >= 400:
        return "fail", f"HTTP {resp.status_code}", None

    # A block page or redirect to a landing page returns 200 with HTML.
    ctype = resp.headers.get("Content-Type", "").lower()
    body_head = resp.content[:400].lstrip().lower()
    looks_html = body_head.startswith(b"<!doctype html") or body_head.startswith(b"<html")

    parsed = feedparser.parse(resp.content)

    if not parsed.entries:
        if looks_html:
            return "fail", f"returned HTML, not a feed (Content-Type: {ctype})", None
        if getattr(parsed, "bozo", False):
            reason = str(getattr(parsed, "bozo_exception", "malformed"))[:70]
            return "fail", f"unparseable: {reason}", None
        return "empty", "valid feed but 0 entries", None

    age = newest_entry_age(parsed)
    latest = parsed.entries[0].get("title", "(untitled)")
    detail = f"{len(parsed.entries)} entries"
    # Always shown, not only under --verbose: a feed that stopped a year ago
    # looks identical to a healthy one on every other number on this line.
    if age is not None and age >= STALE_AFTER_DAYS:
        detail += f" · STALE, newest is {age}d old"
    elif verbose and age is not None:
        detail += f" · newest {age}d"
    if verbose:
        detail += f" · latest: {latest[:55]}"
    if resp.url != url:
        detail += f" · redirected to {resp.url}"
    return "ok", detail, age


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="check a single YAML feed file")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="show the latest headline from each feed")
    args = ap.parse_args()

    if not load_feed_files(args.file):
        print(f"No feed YAML files found in {FEEDS_DIR}")
        return 1

    totals = {"ok": 0, "empty": 0, "fail": 0}
    failures = []
    stale = []

    for feed_file, group in groupby(all_feeds(args.file), key=itemgetter(0)):
        entries = [entry for _, entry in group]
        print(f"\n{feed_file.name}  ({len(entries)} feeds)")
        print("-" * 74)

        for entry in entries:
            name = entry.get("name", "unnamed")
            status, detail, age = check_feed(entry, verbose=args.verbose)
            totals[status] += 1
            feed_stale = age is not None and age >= STALE_AFTER_DAYS

            if status == "ok" and not feed_stale:
                mark, color = "OK  ", OK
            elif status == "ok":
                # Live, parseable, and finished. Not a failure — the exit
                # code stays about feeds that cannot be read — but it must
                # not print as OK either, since wiring it in buys nothing.
                mark, color = "WARN", WARN
                stale.append((name, entry.get("url", ""), age))
            elif status == "empty":
                mark, color = "WARN", WARN
            else:
                mark, color = "FAIL", BAD
                failures.append((name, entry.get("url", ""), detail))

            print(f"  {color}{mark}{END}  {name:<28} {DIM}{detail}{END}")

    print("\n" + "=" * 74)
    print(f"{OK}{totals['ok'] - len(stale)} live{END} · "
          f"{WARN}{len(stale)} stale{END} · "
          f"{WARN}{totals['empty']} empty{END} · "
          f"{BAD}{totals['fail']} failed{END}")

    if stale:
        print(f"\n{WARN}Published nothing in {STALE_AFTER_DAYS}+ days. "
              f"ingest.py drops every item on MAX_AGE_DAYS, so these "
              f"contribute no rows:{END}")
        for name, url, age in stale:
            print(f"  · {name} — newest entry {age}d old\n    {url}")

    if failures:
        print(f"\n{BAD}Fix or remove these before wiring into ingest:{END}")
        for name, url, detail in failures:
            print(f"  · {name}\n    {url}\n    {DIM}{detail}{END}")

    return 0 if totals["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
