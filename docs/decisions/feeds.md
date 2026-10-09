# Feeds

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**Fetch feeds with a browser User-Agent.** Publishers behind Cloudflare return
403s or HTML block pages to unfamiliar agents, and feedparser reports the
latter as a confusing "not well-formed" XML error rather than a network
failure. `src/verify_feeds.py` has working headers — reuse them everywhere
a feed is fetched.

**Feed URLs move constantly.** Never hardcode a URL from memory. Run
`python src/verify_feeds.py -v` after any change to `feeds/`, and treat
that as a required step before wiring a feed into ingest. The `feed-scout`
agent (`.claude/agents/feed-scout.md`) does the legwork — it runs the
checker, finds where a dead feed moved, and proposes the corrected YAML with
evidence — but it only proposes; you still run `verify_feeds.py` and commit.

**And a feed can be live and finished at the same time.** A publication that
stops does not take its feed down: the URL answers 200 for years and
feedparser returns a full item list, so every question of the form "did
entries come back" says yes. What changes is downstream — `ingest.py` drops
each of those items on `MAX_AGE_DAYS`, so the feed contributes no rows at
all. SemiAnalysis was wired into `feeds/tier5_depth.yaml` on 2026-09-22 on
the strength of a clean OK and 10 entries, none newer than Sep 2025, and only
a dry-run ingest caught it. Both checks now measure the newest entry's age
against `verify_feeds.STALE_AFTER_DAYS`: the checker prints it and marks
anything past the bar, and `watch.py` reports it as a FIX. The bar is 60 days
rather than `MAX_AGE_DAYS`' 7 because `watch.py` sends to a chat and a
watcher that cries wolf is one nobody reads — measured over all 65 feeds that
day, the live set ran median 0d, p90 5d, max 7d, and the dead ones 215d, 371d
and 609d. An undated feed has no age and is never reported, which is
`ingest.py`'s own decision about undated rows one layer up.

**A newsroom feed declares where its company announces (2026-10-07).**
`announces` on an entry in `feeds/tier1_primary.yaml` lists the URL prefixes
of that company's own announcements. They are measured from the URLs its
rows actually carry in the sheet, never typed from memory, and re-measured
when a feed moves. `verify_feeds.announcement_prefixes()` is the one reader, and
`draft.py` uses it twice: to label a paperless page under a prefix as its
maker's announcement, and to key a launch's duplicates (see
`voice-and-selection.md` and `dedup.md`). A prefix that is too broad labels
a third party's page as the maker's; one that is too narrow just leaves a
page to the model, so err narrow. Meta AI, `blog.google` and
`developer.chrome.com` have no feed here and so no prefix: their launches
fall back to the model's proposal and the fact-check. Anthropic, xAI and
Cohere publish no feed either, and since 2026-10-09 come in through a
third-party mirror (github.com/Olshansk/rss-feeds) whose links point at the
maker's own pages, so their prefixes work; the mirror can stop silently, and
the 60-day staleness check is the only alarm.

**Prefixes are checked, not trusted.** A site redesign that moves a
newsroom's pages leaves its feed live and its `announces` prefixes silently
wrong. `verify_feeds.announces_drift()` compares each newsroom's newest 10
links with its prefixes and reports the feed when fewer than half fit.
`verify_feeds.py` prints it and `watch.py` makes it a FIX. On 2026-10-07
healthy feeds sat at 9 or 10 of 10; Microsoft Research's one miss was a
podcast.

**A feed can be JSON (2026-10-09).** `kind: hf_daily_papers` marks Hugging
Face's daily papers, which has no RSS — only a free JSON API.
`verify_feeds.parse_feed()` is the one place a feed's bytes become entries,
for both `ingest.py` and the checker, so a new format is one function there
and one `kind`, never a second fetch loop. The papers become
`arxiv.org/abs/<id>` rows, the arXiv feeds' exact URLs, so URL dedupe holds
and `PREPRINT_HOSTS` flags them; a third-party RSS of the same list
(papers.takara.ai) linked its own pages and would have skipped the flag.
`min_upvotes` (10) leaves a paper out until it has the votes — ingest polls
every two hours and stores nothing below the bar, so a paper that climbs is
picked up later. A paper already ingested from arXiv keeps its arXiv row:
the sheet does not learn it was popular.
