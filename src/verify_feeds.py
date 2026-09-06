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
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_DIR = REPO_ROOT / "feeds"
TIMEOUT = 20

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


def check_feed(entry, verbose=False):
    """
    Fetch one feed and classify the result.

    Returns (status, detail) where status is 'ok', 'empty', or 'fail'.
    """
    url = entry.get("url", "")
    if not url:
        return "fail", "no url in entry"

    pace_host(url)
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
    except requests.exceptions.SSLError:
        return "fail", "SSL error — check the certificate or try http://"
    except requests.exceptions.ConnectionError:
        return "fail", "connection failed — domain may be gone"
    except requests.exceptions.Timeout:
        return "fail", f"timed out after {TIMEOUT}s"
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}"

    if resp.status_code == 403:
        return "fail", "HTTP 403 — blocked. Try a different UA or use RSSHub."
    if resp.status_code == 404:
        return "fail", "HTTP 404 — feed moved. Check the site's /rss page."
    if resp.status_code >= 400:
        return "fail", f"HTTP {resp.status_code}"

    # A block page or redirect to a landing page returns 200 with HTML.
    ctype = resp.headers.get("Content-Type", "").lower()
    body_head = resp.content[:400].lstrip().lower()
    looks_html = body_head.startswith(b"<!doctype html") or body_head.startswith(b"<html")

    parsed = feedparser.parse(resp.content)

    if not parsed.entries:
        if looks_html:
            return "fail", f"returned HTML, not a feed (Content-Type: {ctype})"
        if getattr(parsed, "bozo", False):
            reason = str(getattr(parsed, "bozo_exception", "malformed"))[:70]
            return "fail", f"unparseable: {reason}"
        return "empty", "valid feed but 0 entries"

    latest = parsed.entries[0].get("title", "(untitled)")
    detail = f"{len(parsed.entries)} entries"
    if verbose:
        detail += f" · latest: {latest[:55]}"
    if resp.url != url:
        detail += f" · redirected to {resp.url}"
    return "ok", detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="check a single YAML feed file")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="show the latest headline from each feed")
    args = ap.parse_args()

    feed_files = load_feed_files(args.file)
    if not feed_files:
        print(f"No feed YAML files found in {FEEDS_DIR}")
        return 1

    totals = {"ok": 0, "empty": 0, "fail": 0}
    failures = []

    for feed_file in feed_files:
        if not feed_file.exists():
            print(f"{BAD}Missing file:{END} {feed_file}")
            continue

        data = yaml.safe_load(feed_file.read_text()) or {}
        entries = data.get("feeds", [])

        print(f"\n{feed_file.name}  ({len(entries)} feeds)")
        print("-" * 74)

        for entry in entries:
            name = entry.get("name", "unnamed")
            status, detail = check_feed(entry, verbose=args.verbose)
            totals[status] += 1

            if status == "ok":
                mark, color = "OK  ", OK
            elif status == "empty":
                mark, color = "WARN", WARN
            else:
                mark, color = "FAIL", BAD
                failures.append((name, entry.get("url", ""), detail))

            print(f"  {color}{mark}{END}  {name:<28} {DIM}{detail}{END}")

    print("\n" + "=" * 74)
    print(f"{OK}{totals['ok']} live{END} · "
          f"{WARN}{totals['empty']} empty{END} · "
          f"{BAD}{totals['fail']} failed{END}")

    if failures:
        print(f"\n{BAD}Fix or remove these before wiring into ingest:{END}")
        for name, url, detail in failures:
            print(f"  · {name}\n    {url}\n    {DIM}{detail}{END}")

    return 0 if totals["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
