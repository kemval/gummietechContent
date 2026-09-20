# gummietech

Content pipeline for @gummietech — science, technology, and engineering posts
on Instagram.

Strategy and source map: `docs/gummietech_content_system.md`

## Pipeline

```
[1] INGEST → [2] SCORE → [3] DRAFT → [3b] FACT-CHECK → [4] RENDER → [4b] PROOF → [5] HUMAN GATE → [6] PUBLISH → [7] LEARN
  every 2h    Gemini      LLM         against source    HTML→PNG     the slides   10 min/day      Business Suite   saves/shares
```

## Post formats

Four content pillars (`docs` §1). Three of them are carousels and go through
every stage of the pipeline above; the fourth never touches `src/` at all.

| Format | Cadence | Slides | Written by | Template |
|---|---|---|---|---|
| **The Drop** | 3×/week | 5 | `draft.py`, on a cron | `templates/drop.html` |
| **The Breakdown** | 1×/week | 8–10 | a person | `templates/breakdown.html` |
| **The Signal** | optional | 5 items | `draft.py --signal` | `templates/signal.html` |
| **The Build** | 2×/week | — | a person, start to finish | reel, not a carousel |

"Written by" is about the words only. A hand-written Breakdown is a JSON file
in `posts/` that goes through exactly the machinery a Drop does — render,
proof, fact-check, Telegram, the archive. It is hand-written because that is
the format where the explanation has to be excellent (`docs` §4); a Signal's
per-item claim is a hook rather than a mechanism, so the pipeline writes it:

```bash
python src/draft.py --signal      # the top five queued rows nobody drafted
```

That walks the queue five times instead of once, resolves each item's paper
through Crossref for its own `attribution` and `peer_reviewed`, and spends
one LLM call on the five claims. The order the sources go into the prompt is
the only thing tying a claim to its credit, so a reply of the wrong length is
refused rather than zipped against whatever lines up.

`src/formats.py` is the one table that says what each format is made of, and
every other module asks it rather than branching on `post_type`. A Breakdown
takes `the_question`, `the_intuition` and a `mechanism` list where a Drop
takes `what_happened`; a Signal takes `items`, five objects that each carry
their own `attribution`, `source_url` and `peer_reviewed`, because a roundup
has five sources and crediting one of them credits none. How many slides a
format has is its template's business: `render.py` counts `.slide` divs, so
adding a format is adding a template.

`posts/era.json`, `posts/era-breakdown.json` and `posts/era-signal.json` are
the fixtures CI renders — one per format, no date prefix, never published.

## Layout

| Path | Purpose |
|---|---|
| `src/` | Pipeline scripts |
| `feeds/` | RSS source lists by tier (YAML) |
| `templates/` | HTML/CSS slide and site templates |
| `posts/` | Drafted post JSON |
| `output/` | Rendered PNGs (gitignored) |
| `site/` | Built web archive (gitignored) |
| `.github/workflows/` | GitHub Actions cron |

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill in keys
```

## The drafting run

`daily.yml` drafts, translates and renders one post on Monday, Wednesday and
Friday — the three Drops the cadence is fixed at — then sends the slides and
`caption.txt` to Telegram. You post the carousel to Instagram
yourself and tap **Posted to Instagram**; `publish.yml` sees the tap on its
next poll, stamps `published_at`, and rebuilds the archive. That poll asks
for every 15 minutes and the free tier gives it about every two hours, so
allow a couple of hours rather than minutes.

Set up once:

1. Message **@BotFather** on Telegram, `/newbot`, keep the token.
2. Message your new bot anything, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy
   `result[0].message.chat.id`.
3. Add repo secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, and the repo
   variable `PUBLISH_TZ` (e.g. `America/Bogota`) so `published_at` is dated in
   your timezone rather than UTC.

Locally, the same two steps are:

```bash
python src/telegram.py send posts/2026-09-15-example.json   # after render.py
python src/telegram.py confirm                              # after you tap
```

Both reviews run before the message is sent, and either one failing withholds
the button, so a bad post cannot be marked live from your phone:

- **`src/proof.py`** measures the rendered layout — text crossing the ink
  frame, content clipped past it, contrast under 4.5:1, a missing preprint
  flag, a broken colorway rhythm. No credentials, runs anywhere:

  ```bash
  python src/proof.py posts/2026-09-15-example.json   # exits 1 on BLOCK
  ```

- **`fact-check`** verifies the claims against the source, running as a Claude
  Code agent in CI. It uses your **Pro subscription rather than API billing**:
  run `claude setup-token` and add the result as the repo secret
  `CLAUDE_CODE_OAUTH_TOKEN`. Leave that secret unset and the step is simply
  skipped — the message tells you nothing checked the claims.

For a post that really matters, draft locally and run the `slide-proof` agent
too: it judges how the slides *look*, which is the part no measurement
answers.

## Measuring

Three days after a post goes live, the same poll that watches for the publish
tap asks that post for its numbers in the approval chat. Reply with three
integers — saves, shares, profile visits — and they land in the post's own
JSON:

```bash
python src/learn.py               # medians by format, colorway, domain, weekday
```

Saves and shares are the growth metrics, profile visits the funnel one; likes
are deliberately not tracked. `learn.py` holds back any group under three
posts rather than ranking noise, and says so until there are thirty measured
posts, which is where the cut-the-weakest-format decision belongs.

The asking half needs `TELEGRAM_CHAT_ID` in the `publish` workflow. Leave it
unset and nothing is asked; the publish tap is unaffected.

## Web archive

Instagram does not make caption URLs clickable, so the source of a carousel
never reaches a reader. The archive is where the bio link points:

<https://kemval.github.io/gummietechContent/>

```bash
python src/translate.py           # adds the Spanish `es` block to posts
python src/site.py                # builds site/ from posts/*.json
```

One page per carousel, built entirely from JSON the drafting step already
produces — no writing per post. A post appears **only** once it has a
`published_at` date, which you add by hand when it actually goes live on
Instagram. Without that gate, `draft.py` would put unreviewed drafts on the
open web. Pushing to `master` rebuilds and deploys it.

Pages are bilingual: the globe in the masthead switches between English and
Spanish and remembers the choice. The Spanish comes from each post's `es`
block, machine-written by `translate.py` on the same free LLM tier as
scoring, so read it before the post goes live — it lands on a permalink.
Posts without a complete `es` block simply stay English.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Offline and fast — no network, no LLM, no browser. Every test is a case the
pipeline has already got wrong once, which is the bar for adding one. CI runs
them on every push alongside the end-to-end smoke check.

## Feeds

Three tiers in `feeds/`, by how close a source is to where news is born
(`docs` §3):

| File | Sources | What it is |
|---|---|---|
| `tier1_primary.yaml` | 51 | Labs, agencies, company newsrooms, journal press feeds |
| `tier2_preprints.yaml` | 10 | arXiv and bioRxiv — papers, not coverage of them |
| `tier3_signal.yaml` | 2 | Where a story is already being reacted to |

Tier 2 is the one that pays for `draft.py` twice over: every item is the
paper itself, so there is no news article to get behind, and every host is in
`PREPRINT_HOSTS` — the post is `peer_reviewed: false` whatever Crossref says
and the slide must carry the flag. It arrives over `rss.arxiv.org`, the daily
announcement, rather than the arXiv API, which throttled every category query
past what an unattended 2-hourly job can absorb. Nothing is announced at a
weekend, so those seven feeds legitimately verify as 0 entries on a Saturday
or a Sunday. The feed file's header carries the measurements.

Feed URLs move constantly. Check which ones are live before relying on them,
and always after editing a tier:

```bash
python src/verify_feeds.py            # -v for every URL, not just the failures
```

The `feed-scout` agent finds where a dead feed moved and proposes the
corrected YAML; you still run the checker and commit.

## Budget

$0/month. Every dependency is free tier, open source, or self-hosted.
Do not add a paid service without replacing it in `docs/`.
