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

## Web archive

Instagram does not make caption URLs clickable, so the source of a carousel
never reaches a reader. The archive is where the bio link points:

<https://kemval.github.io/gummietechContent/>

```bash
python src/site.py                # builds site/ from posts/*.json
```

One page per carousel, built entirely from JSON the drafting step already
produces — no writing per post. A post appears **only** once it has a
`published_at` date, which you add by hand when it actually goes live on
Instagram. Without that gate, `draft.py` would put unreviewed drafts on the
open web. Pushing to `master` rebuilds and deploys it.

## Verify feeds

Feed URLs move. Check which ones are live before relying on them:

```bash
python src/verify_feeds.py
```

## Budget

$0/month. Every dependency is free tier, open source, or self-hosted.
Do not add a paid service without replacing it in `docs/`.
