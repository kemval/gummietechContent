# gummietech

Content pipeline for @gummietech — daily science, technology, and engineering
posts on Instagram.

Strategy and source map: `docs/gummietech_content_system.md`

## Pipeline

```
[1] INGEST → [2] SCORE → [3] DRAFT → [4] DESIGN → [5] HUMAN GATE → [6] PUBLISH
  every 2h    Gemini      LLM         HTML→PNG      10 min/day      Business Suite
```

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

## Daily run

`daily.yml` drafts, translates and renders one post a day, then sends the
five slides and `caption.txt` to Telegram. You post the carousel to Instagram
yourself and tap **Posted to Instagram**; `publish.yml` sees the tap within
the hour, stamps `published_at`, and rebuilds the archive.

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

## Verify feeds

Feed URLs move. Check which ones are live before relying on them:

```bash
python src/verify_feeds.py
```

## Budget

$0/month. Every dependency is free tier, open source, or self-hosted.
Do not add a paid service without replacing it in `docs/`.
