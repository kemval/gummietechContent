#!/usr/bin/env python3
"""
Layer 1: pull every feed in feeds/*.yaml and append new items to the sheet.

Fetch → keyword pre-filter → dedupe against what's already in the sheet →
one batched append. Scoring happens later, in score.py.

Usage:
    python src/ingest.py
    python src/ingest.py --dry-run                 # fetch and report, write nothing
    python src/ingest.py --file feeds/tier1_primary.yaml

Environment (.env locally, repo secrets in CI):
    GOOGLE_SHEET_ID              the spreadsheet key from its URL
    GOOGLE_SHEETS_CREDENTIALS    path to the service account JSON

Two constraints shape this file:

  - Feeds are fetched with a browser User-Agent, reusing verify_feeds.HEADERS,
    and paced per host so grouped feeds on one domain do not earn a 429.
    Publishers behind Cloudflare answer unfamiliar agents with a 403 or an
    HTML block page, and feedparser reports the latter as a confusing
    "not well-formed" XML error rather than a network failure.

  - Funding and PR items are dropped here, before they ever reach the sheet.
    Gemini's free tier has a daily request cap, so every junk row that
    survives ingest costs part of the day's scoring budget.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gspread
import requests
import yaml
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from verify_feeds import HEADERS, TIMEOUT, pace_host, parse_feed

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_DIR = REPO_ROOT / "feeds"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column order of the sheet. score.py fills `score`, `notes` and `beat` and
# moves `status` on from "new", so anything appended here leaves those blank.
# `topic` is the feed's, from feeds/*.yaml; `beat` is the item's own, from
# the scorer, because a feed is not a subject — Phys.org carries AI and Tech
# Xplore carries batteries. New columns go on the end: ensure_header()
# rewrites row 1 when this list changes, and nothing already written moves.
COLUMNS = ["url", "title", "summary", "source", "topic",
           "published", "fetched_at", "status", "score", "notes", "beat"]

# Feeds carry weeks of backlog. Without a window, the first run floods the
# sheet with stale items that will never be worth posting.
MAX_AGE_DAYS = 7

SUMMARY_CHARS = 500

# How old a queued story may be and still be drafted. The queue keeps every
# row it ever scored, and ranking is by score alone, so on 2026-10-07 it
# held 3,227 queued rows, most of them from September. A launch drafted from
# one of those — GPT-6 Astra, 34 days old and already replaced — went out
# saying "just launched". The account's promise is to keep a reader ahead
# of the news, and month-old news does not. Older rows stay queued in the
# sheet; they are only no longer chosen. --row is the override.
MAX_STORY_AGE_DAYS = 10


def story_age_days(row: list[str], col: dict, now: datetime) -> float | None:
    """Days since the story was published, else since it was fetched.

    None when neither date reads, which pick_row treats as too old: a row
    that cannot show it is fresh is not drafted as news.
    """
    for name in ("published", "fetched_at"):
        if name not in col or col[name] >= len(row):
            continue
        try:
            when = datetime.fromisoformat(row[col[name]])
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (now - when).total_seconds() / 86400
    return None



# Substring match against title + summary, lowercased. Funding rounds and
# partnership announcements are business news, not science or engineering.
#
# The second group is recurring filler from the general-interest science
# press: daily photo posts, anniversary columns, and affiliate commerce.
# These are structural, not topical — a title matching one of them is
# never a story, so dropping them here costs nothing and keeps a
# predictable ~15 rows a week out of the day's scoring budget.
#
# "reading list" is the same shape one tier down. An essay newsletter is
# ingestible only while one item is one story, and feeds/tier5_depth.yaml's
# header is the test; Construction Physics fails it about half the time by
# publishing a links column under that name — 11 of 20 items on 2026-09-22.
# A substring, not a prefix match, because the separator moves between
# issues ("Reading List 09/19/2026", "Reading List — 09/12/2026").
DROP_PATTERNS = [
    "raises $", "series a", "series b", "series c", "seed round",
    "announces partnership", "partners with", "acquires", "acquisition of",
    "appoints", "names new ceo", "quarterly results", "earnings",
    "webinar", "sponsored", "press release",
    "photo of the day", "on this day in space", "best deals", "% off",
    "reading list",
]

TAG_RE = re.compile(r"<[^>]+>")


def clean_text(raw: str, limit: int = SUMMARY_CHARS) -> str:
    """Feed summaries are HTML fragments; the sheet wants plain text."""
    text = html.unescape(TAG_RE.sub(" ", raw or ""))
    text = " ".join(text.split())
    return text[:limit]


def entry_published(entry) -> datetime | None:
    """Best-effort publication time, as an aware UTC datetime."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def is_noise(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}".lower()
    return any(pattern in haystack for pattern in DROP_PATTERNS)


def fetch_feed(feed: dict) -> tuple[list[dict], str | None]:
    """
    Fetch and parse one feed.

    Returns (items, error). A failing feed is never fatal — one dead
    publisher must not take down a scheduled run — so the caller reports
    the error and moves on.
    """
    url = feed.get("url", "")
    name = feed.get("name", "unnamed")
    topic = feed.get("topic", "")
    if not url:
        return [], "no url in entry"

    pace_host(url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)
    except requests.exceptions.Timeout:
        return [], f"timed out after {TIMEOUT}s — skipped this run"
    except requests.exceptions.RequestException as exc:
        return [], f"{type(exc).__name__}: {exc} — check the URL in feeds/"

    if resp.status_code >= 400:
        return [], (f"HTTP {resp.status_code} — re-run "
                    f"`python src/verify_feeds.py -v` and fix feeds/")

    # parse_feed, not feedparser directly: a feed's `kind` can name a JSON
    # source (Hugging Face's daily papers) that verify_feeds turns into
    # entries, so the checker and the ingest read it the same way.
    parsed = parse_feed(feed, resp.content)
    if not parsed.entries:
        return [], "0 entries — feed may have moved; verify_feeds.py will say"

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    items = []

    # Two volume controls a feed entry can ask for, for the arXiv mega-
    # categories (feeds/tier2_preprints.yaml). `new_only` keeps first
    # announcements and drops cross-lists and replacement versions, which
    # arXiv tags on each item and which would otherwise be scored again under
    # a second category. `max_items` caps what one fetch may add, because a
    # day of cs.AI is ~127 papers and every one of them costs score.py quota.
    new_only = bool(feed.get("new_only"))
    max_items = int(feed.get("max_items") or 0)

    for entry in parsed.entries:
        if max_items and len(items) >= max_items:
            break
        if new_only and entry.get("arxiv_announce_type", "new") != "new":
            continue
        # A trailing backslash is not part of any URL: one Hacker News row
        # arrived as mistral.ai/news/mistral-large-4/\ and 404'd, so the
        # maker's own announcement could not be read (2026-10-07).
        link = (entry.get("link") or "").strip().rstrip("\\")
        title = clean_text(entry.get("title", ""), limit=300)
        if not link or not title:
            continue

        published = entry_published(entry)
        # Undated entries are kept: some feeds omit dates entirely, and
        # dropping them would silently lose whole sources.
        if published and published < cutoff:
            continue

        summary = clean_text(entry.get("summary", "") or
                             entry.get("description", ""))
        if is_noise(title, summary):
            continue

        items.append({
            "url": link,
            "title": title,
            "summary": summary,
            "source": name,
            "topic": topic,
            "published": published.isoformat(timespec="seconds") if published else "",
            "fetched_at": fetched_at,
            "status": "new",
            "score": "",
            "notes": "",
            "beat": "",
        })

    return items, None


def open_sheet():
    """Open the first worksheet of the configured spreadsheet."""
    load_dotenv(REPO_ROOT / ".env")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    creds_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "credentials.json")
    if not sheet_id:
        sys.exit("GOOGLE_SHEET_ID is not set. Add it to .env "
                 "(locally) or the repo secrets (CI).")

    creds_file = Path(creds_path)
    if not creds_file.is_absolute():
        creds_file = REPO_ROOT / creds_file
    if not creds_file.exists():
        sys.exit(f"No service account file at {creds_file}. Download the JSON "
                 "key from Google Cloud and point GOOGLE_SHEETS_CREDENTIALS at it.")

    creds = Credentials.from_service_account_file(str(creds_file), scopes=SCOPES)
    try:
        return gspread.authorize(creds).open_by_key(sheet_id).sheet1
    except gspread.exceptions.APIError as exc:
        sys.exit(f"Google rejected the request: {exc}\n"
                 "Check that the Sheets API is enabled for the service account's "
                 "project and that the sheet is shared with its client_email.")
    except PermissionError:
        sys.exit("The service account cannot open this sheet. Share the sheet "
                 "with the client_email in the credentials JSON, as Editor.")


def existing_urls(worksheet) -> set[str]:
    """URLs already in the sheet. One read, not one per row."""
    column = worksheet.col_values(COLUMNS.index("url") + 1)
    return set(column[1:]) if column else set()


def ensure_header(worksheet) -> None:
    if worksheet.row_values(1) != COLUMNS:
        # The grid is exactly as wide as the columns it was created with, and
        # writing past its edge is an error rather than a resize.
        if worksheet.col_count < len(COLUMNS):
            worksheet.add_cols(len(COLUMNS) - worksheet.col_count)
        worksheet.update(values=[COLUMNS], range_name="A1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="ingest a single YAML feed file")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and report without writing to the sheet")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
        feed_files = [path if path.is_absolute() else REPO_ROOT / path]
    else:
        feed_files = sorted(FEEDS_DIR.glob("*.yaml"))
    if not feed_files:
        sys.exit(f"No feed YAML files found in {FEEDS_DIR}")

    worksheet = None if args.dry_run else open_sheet()
    if worksheet is not None:
        ensure_header(worksheet)
        seen = existing_urls(worksheet)
        print(f"Sheet has {len(seen)} items already")
    else:
        seen = set()
        print("Dry run — nothing will be written")

    fresh: list[dict] = []
    failures: list[tuple[str, str]] = []
    feeds_read = 0

    for feed_file in feed_files:
        if not feed_file.exists():
            failures.append((feed_file.name, "file not found"))
            continue

        data = yaml.safe_load(feed_file.read_text()) or {}
        feeds = data.get("feeds", [])
        print(f"\n{feed_file.name}  ({len(feeds)} feeds)")

        for feed in feeds:
            name = feed.get("name", "unnamed")
            items, error = fetch_feed(feed)
            if error:
                failures.append((name, error))
                print(f"  FAIL  {name:<28} {error}")
                continue

            feeds_read += 1
            new = [i for i in items if i["url"] not in seen]
            seen.update(i["url"] for i in new)
            fresh.extend(new)
            print(f"  ok    {name:<28} {len(items):>3} recent, {len(new):>3} new")

    print(f"\n{len(fresh)} new items from {feeds_read} feeds")

    if fresh and worksheet is not None:
        # One append call, not one per row: the Sheets API allows 60 writes
        # per minute per user, and a busy run can produce hundreds of rows.
        worksheet.append_rows([[item[c] for c in COLUMNS] for item in fresh],
                              value_input_option="RAW")
        print(f"Appended {len(fresh)} rows")

    if failures:
        print(f"\n{len(failures)} feed(s) failed:")
        for name, error in failures:
            print(f"  · {name}: {error}")

    # A run where every feed failed is a real breakage (network, or a stale
    # feed list); a run where some failed is normal and should not fail CI.
    return 1 if feeds_read == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
