# gummietech — Content System & Automation Plan

**Account:** @gummietech (Instagram)
**Niche:** Science · Technology · Engineering
**Goal:** Daily publishing, automated pipeline, audience growth through saves and shares
**Budget:** $0/month. Every tool in this document is free. See §4.
**Owner location:** Costa Rica (UTC−6) — relevant for posting-time decisions
**Version:** 1.1 — September 2026 (zero-budget revision)

---

## 0. Strategic premise

The instinct to "post first, before every other creator" is the wrong north star, and building the system around it wastes effort.

Instagram is not a real-time platform. The feed is not chronological, and a post from six hours ago routinely outperforms one from six minutes ago. Speed matters only *relative to other science/tech Instagram pages*, and even then it is not what drives growth. **Saves and shares are.**

The corrected target:

> Fast enough to feel current. Explained better than anyone else. Designed to be saved.

Four constraints that shape every decision below:

1. **Depth beats speed.** The differentiator is the "why it matters" and the "here's the catch," not the headline.
2. **Evergreen content is not optional.** Most days there is no news worth posting. A library of timeless posts is what makes daily publishing survivable.
3. **Credibility is the whole asset.** In science content, one confidently-wrong post costs more than ten good posts earn. This is why the human approval gate is non-negotiable.
4. **Zero budget.** Free tools only. This is a real constraint, not a preference, and it changes almost nothing about what is achievable — the paid tools on the original plan bought convenience, not capability.

---

## 1. Content formats

Lock these before automating anything. Automation amplifies whatever format it is fed.

### Post types

| Type | Frequency | Purpose | Format |
|---|---|---|---|
| **The Drop** | 4–5×/week | Breaking news, fast | Carousel, 5 slides |
| **The Breakdown** | 1–2×/week | Explain a concept behind a recent story | Carousel, 8–10 slides |
| **The Signal** | 1×/week | Weekly roundup: "5 things you missed" | Carousel or Reel |

### The Drop — 5-slide template (the daily engine)

1. **Hook** — the claim in huge type, one visual. *"A robot just learned to fold laundry from watching 3 videos."*
2. **What happened** — 25 words maximum.
3. **Why it matters** — the part every other page skips. **This is the brand.**
4. **The catch** — limitation, unproven claim, reason for skepticism. Rare on tech IG; builds trust fast.
5. **CTA + source** — "Follow @gummietech" + paper name / DOI / link.

Slides 3 and 4 are the entire competitive advantage. Anyone can rewrite a headline. Almost nobody adds the *why* and the *but*.

### The Breakdown — 8–10 slides

Cover → the question → the intuition → the mechanism (2–3 slides) → the surprising implication → the limits → recap → CTA.

### The Signal — weekly

Five items, one slide each, ranked. Highest save rate of the three formats because it functions as a reference.

---

## 2. Pipeline architecture

Seven layers. Build in order. Do not attempt the whole thing at once.

```
[1] INGEST → [2] SCORE → [3] DRAFT → [3b] FACT-CHECK → [4] DESIGN → [4b] PROOF → [5] HUMAN GATE → [6] PUBLISH → [7] LEARN
  every 2h    free LLM     LLM        against source    HTML→PNG    the render    10 min/day     Business Suite   weekly
```

### Layer 1 — Ingest (every 2 hours)

A Python script using `feedparser` pulls all sources into one sheet or table with columns:
`title · url · source · source_tier · raw_text · published_at · score · status · attribution`

No aggregation service required — parsing RSS directly in code costs nothing and gives full control over filtering. Runs on GitHub Actions (see §4).

### Layer 2 — Filter & rank (LLM scoring)

Every item scored 1–10 on four axes. Only items scoring ≥7 total surface in the morning queue.

- **Novelty** — genuinely new, or a rehash?
- **Visual potential** — is there an image, diagram, or video? No visual = hard to post.
- **Explainability** — can a smart non-expert get it in 5 slides?
- **Surprise** — does it violate an intuition? This is the share driver.

Reject automatically: funding rounds, product launches with no technical substance, opinion pieces, listicles, anything already covered by three or more large accounts.

Run this on a free-tier LLM (Gemini Flash or Groq). Scoring is a cheap, high-volume task — it does not need a frontier model. Batch the calls and sleep between them to respect rate limits.

### Layer 3 — Draft

Feed the winning item plus full source text to an LLM with a locked prompt returning strict JSON:

```json
{
  "post_type": "drop | breakdown | signal",
  "hook": "...",
  "what_happened": "...",
  "why_it_matters": "...",
  "the_catch": "...",
  "caption": "...",
  "keywords": ["..."],
  "hashtags": ["..."],
  "alt_text": "...",
  "source_url": "...",
  "attribution": "...",
  "peer_reviewed": true
}
```

JSON output is the key architectural move — it plugs straight into the design layer with zero copy-paste.

Split the work by stakes: free-tier LLM for routine Drops, this Claude project for Breakdowns and anything where the explanation has to be excellent.

### Layer 3b — Fact-check (before it costs a render)

Layer 3 is an LLM reading a fetched article, and when that fetch is blocked or thin it drafts from the feed summary instead. What comes back is fluent, plausible and sometimes wrong: a number that is not in the paper, a limitation nobody stated, a citation crediting the press office instead of the authors. None of that is visible in the JSON. Only the source settles it.

`.claude/agents/fact-check.md` defines a read-only agent that re-fetches `source_url`, finds the underlying paper behind the news coverage, and checks each slide claim against it — every number and name must appear in the source, `the_catch` must be a limitation the source itself states, the hedges ("suggests", "in mice", "in simulation") must survive onto the slide, and `attribution` must name the paper's first author rather than the university that wrote the release. It returns BLOCK / FIX / PASS per claim with the quoted sentence, and a source it cannot read is UNVERIFIED — a hold, not a pass.

It reports; it never edits the JSON, renders, or dates a post. That keeps §7.1 intact: this layer makes the gate cheaper to run, it does not stand in for it.

Deterministic checks stay in code, where they already are — `draft.py` and `render.py` hard-fail on missing `attribution` or `alt_text`, on a non-boolean `peer_reviewed`, and on a preprint host claiming peer review. The agent exists for the one question code cannot answer: *does the source actually say this.* One case is worth calling out because the host check structurally cannot see it — coverage on a journal or news domain reporting work that is itself a preprint.

Run it before Layer 4 rather than after. A render that has to be thrown away costs Playwright time and a Business Suite upload; a caught claim costs nothing.

### Layer 4 — Design (automated rendering)

**HTML/CSS template rendered to PNG via Playwright.** Free, headless, perfect typography, infinitely customizable, and it produces better output than the template tools anyway.

Fonts from Google Fonts (free, self-hostable). Icons from Lucide or Tabler (free, open source). Diagrams and charts drawn in SVG inside the same template.

Output: 1080×1350 PNG per slide.

*Note: Canva's Bulk Create is a Pro feature and is not available on the free plan. Canva free is still useful for one-off manual designs, but the automated path is HTML→PNG. Figma's free tier works for designing the template visually before translating it to HTML.*

### Layer 4b — Proof the render (before the gate spends attention on it)

`render.py` screenshots each slide at a fixed 1080×1350 but never inspects the
result, and it sizes the hook from a character count rather than a measured
layout. A long compound word, a body slide a few words over the 25-word rule,
or a colorway rotation that lands pale ink type on a washed-out field can
overflow the frame, fail contrast, or push the "Preprint — not yet
peer-reviewed" flag off slide 4 — with no error, because nothing in code
looks at the pixels.

`.claude/agents/slide-proof.md` is a read-only agent that renders the post to
a scratch directory, reads the five PNGs, and reports BLOCK / FIX / PASS on
frame containment, hook sizing, the `lead · cream · support · dark · lead`
rhythm, preprint-flag visibility, contrast, and the attribution line — the
failures only the rendered image reveals. It never edits the JSON, never
renders into `output/`, and never dates a post. It is the visual counterpart
to Layer 3b: 3b checks whether the words are true, 4b checks whether they are
legible on the slide. Run both before Layer 5 so the ten-minute review goes to
judgement, not to spotting clipped text.

### Layer 5 — Human gate (DO NOT SKIP)

A 10-minute morning review in the sheet: approve / edit / kill. Approve flips status to `approved`. Read the Layer 3b report alongside the slides — it tells you which claims were verified against the source and which were not, so the ten minutes go to judgement rather than to re-reading the paper.

A fully autonomous science account will eventually post something wrong or embarrassing. In this niche that is unrecoverable. The gate stays.

### Layer 6 — Publish

**Route A — Meta Business Suite (start here, free, no API).**
Once the Instagram account is Professional and linked to a Facebook Page, Meta's own Business Suite Planner schedules Instagram posts including carousels, with a calendar view, at no cost and with no post cap. This is Meta's first-party tool, which is why it has none of the free-tier limits third-party schedulers impose (Buffer free caps queued posts; Later free caps monthly posts).

Daily flow: approve in the sheet → upload the rendered PNGs to Business Suite → paste caption and alt text → schedule. About 5 minutes.

**Route B — Instagram Graph API (later, also free, but gated by setup).**
The API itself costs nothing. The friction is approval and configuration, not money.

- Requires a Facebook Business account, a linked Facebook Page, an Instagram **Professional** account (personal accounts have no API access), a Meta developer app, and approved content-publishing permission. App review runs roughly 2–4 weeks per permission.
- Publishing is two calls: `POST /{ig-user-id}/media` to create a container, then `POST /{ig-user-id}/media_publish`.
- **There is no native scheduling endpoint** — no `scheduled_publish_time` parameter like the Facebook Pages API has. Scheduling must be built with cron or a task queue.
- Limit: **50 API-published posts per rolling 24 hours.** A carousel counts as one.
- Media must be hosted at a publicly accessible URL at publish time — GitHub Pages or Cloudflare R2's free tier both work.

Move to Route B only once the format is proven and the manual scheduling step is genuinely the bottleneck.

### Layer 6b — The archive (the link in bio)

Instagram does not make caption URLs clickable. `source_url` is drafted, rendered into `caption.txt`, and printed on slide 5 as flat text — and then dies there. Nobody can reach the paper.

`src/site.py` builds `posts/*.json` into a static site on GitHub Pages: an index plus one permalink per carousel, showing the same five slide texts as readable HTML with a real link to the source, the code, the attribution, and the preprint label. Slide 5 carries "Full sources → link in bio".

**This is deliberately not a blog.** A blog is a second content product — original long-form writing per post, forever, competing for the 20 minutes/day §8 budgets. The archive costs nothing per post because it is a pure function of the drafting JSON. If the appetite for writing long-form ever appears, that is a separate decision, not an extension of this.

A post reaches the site only when it has a `published_at` date, added by hand when it actually goes live on Instagram. `draft.py` writes into `posts/` *before* approval, so without that gate an unreviewed draft would land on a public permalink — §7.1 applies to the web at least as hard as it applies to the feed.

Secondary benefit: Route B needs media at a publicly accessible URL, and this puts that hosting in place already.

### Layer 7 — Learn (weekly)

Instagram Insights (native, free) gives saves and shares per post. Log them in a sheet manually. Track **saves and shares**, not likes. After 30 posts, cut the weakest format and double the winner.

---

## 3. Source map

All sources below are free. Anything paid is flagged.

### Tier 1 — Primary sources (where news is born)

Journalists write *from* these. Reading them directly puts you level with reporters and ahead of aggregators.

**Research institutions:** MIT News, Stanford Engineering, Caltech, Berkeley News, ETH Zurich, Max Planck, CERN, Fermilab, NASA (JPL + main newsroom), ESA, NOAA, Argonne, Oak Ridge, LBNL, Wellcome Sanger.

**Company newsrooms** — for AI/tech, news drops here first: OpenAI, Google DeepMind, Anthropic, Meta AI, NVIDIA (newsroom + developer blog), Boston Dynamics, SpaceX, Waymo, Figure, Apple Newsroom, Hugging Face.

**Journal press feeds:** Nature news, Science news, Cell Press, PNAS, PLOS.

Most expose RSS at `/news/feed`, `/rss`, or `/feed`. Verify each URL loads before saving — publishers move these.

### Tier 2 — Preprints (genuinely ahead of the news cycle)

- **arXiv API** — free, no key. Categories: `cs.AI`, `cs.LG`, `cs.RO`, `quant-ph`, `cond-mat.mtrl-sci`, `astro-ph`. Sort by `submittedDate`.
- **bioRxiv / medRxiv API** — free, JSON.
- **Papers with Code** and **Hugging Face Daily Papers** — free, pre-filtered for traction, cuts arXiv's noise.
- **Semantic Scholar API** — free key, exposes citation velocity to spot papers suddenly getting picked up.

⚠️ **Preprints are not peer-reviewed.** Always label them as such on-slide. See §7.

### Tier 3 — Community signal (where things go viral first)

- **Hacker News Algolia API** — free, no key. `search_by_date` with `points>150`. Best early-warning system for tech.
- **Reddit** — r/science, r/technology, r/Futurology, r/MachineLearning, r/EngineeringPorn, r/askscience. Append `.rss` to any subreddit URL. Free.
- **GitHub Trending** — daily, filtered by language. Free.
- **Product Hunt API** — free tier; new tools, feeds a weekly "3 tools you should know."
- **Bluesky** — real, free, open API. Build a list of ~200 researchers and labs and pull the firehose. This is where the science community migrated, and unlike X it costs nothing to read programmatically.

*Not used: the X/Twitter API. Its read tiers are paid and the free tier does not support this use case.*

### Tier 4 — Curated newsletters (highest quality per minute, all free)

Humans doing Layer 2 filtering for free. Subscribe with a dedicated Gmail, then pull that inbox into the pipeline via the Gmail API (free) so newsletters become just another feed.

**AI:** Import AI (Jack Clark), The Batch (Andrew Ng), AlphaSignal, TLDR AI, Last Week in AI, Ahead of AI (Sebastian Raschka)
**Science:** Nature Briefing, Science Adviser, Quanta, STAT Morning Rounds
**Tech/Engineering:** IEEE Spectrum Tech Alert, Benedict Evans, Stratechery (free tier), The Pragmatic Engineer (free tier), Hacker Newsletter
**Space:** Payload, Rocket Report (Ars Technica)

### Tier 5 — Depth layer: Medium, Substack, Stack Exchange

**Not breaking-news sources.** They publish *after* the news. Their value is supplying the understanding and the angle that makes slide 3 better than everyone else's.

**Medium** — RSS works and is free; insert `/feed` immediately after `medium.com`:
```
medium.com/feed/@username                     → author
medium.com/feed/tag/artificial-intelligence   → topic
medium.com/feed/[publication-slug]            → publication
medium.com/feed/[publication]/tagged/[tag]    → publication + tag
customdomain.com/feed                         → custom-domain publications
```
The `@` in profile feeds is mandatory. Custom-domain publications still proxy back to medium.com. **Paywalled posts are truncated to a preview in RSS — never full text.**

Follow specific authors and engineering publications, never raw tags — Medium's tag feeds are overwhelmingly low-effort SEO content, especially anything tagged AI. Worth following: Netflix Tech Blog (`netflixtechblog.com/feed`), Towards Data Science, Better Programming, Google Developers, Airbnb Engineering, Pinterest Engineering.

**Substack** — better than Medium by a wide margin, and RSS is free on every publication: `https://[publication].substack.com/feed`, or append `/feed` on custom domains.

Recommended: Import AI, Interconnects (Nathan Lambert), Understanding AI (Timothy Lee), Astral Codex Ten, **Construction Physics** (Brian Potter — outstanding for engineering), Noahpinion, Semianalysis, Payload, Exponential View. Also check **Substack Notes** manually as a discovery layer.

**Stack Exchange** — reframe entirely: this is not news, it is a live map of what people are confused about, which makes it the best source of educational post ideas available.

API — free, ~300 requests/day unauthenticated, ~10,000 with a free key, no OAuth for public reads:
```
https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged=machine-learning&site=stackoverflow
```
Per-tag RSS: `https://stackoverflow.com/feeds/tag/[tag]`

The sites that matter for gummietech are Stack Overflow's siblings:

| Site | Goldmine |
|---|---|
| physics.stackexchange.com | "Why does X happen?" with expert answers |
| engineering.stackexchange.com | Real-world design tradeoffs |
| space.stackexchange.com | Orbital mechanics, mission design |
| ai.stackexchange.com | Conceptual ML, not code |
| chemistry / biology / earthscience | Same pattern |
| worldbuilding.stackexchange.com | Underrated — "what if" physics, highly shareable |

**The play:** query each site sorted by all-time votes, pull the top 200 questions → a 200-post content calendar of questions people genuinely want answered, with expert answers already attached. Sort by `activity` instead to see what's hot this week.

**Similar platforms, all free:**

| Platform | Feed / API | Why |
|---|---|---|
| Dev.to | `dev.to/feed`, `/feed/tag/[tag]`, Forem API | Higher signal than Medium, no paywall |
| Hashnode | GraphQL API | Dev writing, clean data |
| Lobste.rs | `lobste.rs/rss` | Smaller, much higher quality than HN |
| LessWrong / Alignment Forum | GraphQL API | Deep AI thinking pre-mainstream |
| Ghost blogs | `[site]/rss` | Most independent tech blogs run Ghost |
| The Gradient, Quanta, Asterisk | RSS | Long-form, excellent carousel material |

### Tier 6 — Evergreen library (NOT a news pipeline)

Educational content, fun facts, and ideas are time-independent and non-competitive. This is what actually builds a following, because it gets saved and re-shared for years. Build it as a **separate batch-produced library** — a buffer so no day is ever missed.

Doubly important on a zero budget: evergreen posts have no API cost, no rate limits, and no deadline.

| Source | What you get |
|---|---|
| Wikipedia "Unusual articles" | Endless genuinely weird, true facts |
| Kurzgesagt / Veritasium / 3Blue1Brown / Real Engineering back catalogs | Proven-viral concepts, reformattable for IG |
| Quanta archive | Best science explainers written anywhere |
| Nature "Milestones" series | History of science, ideal for carousels |
| Wolfram MathWorld, NASA APOD, USGS, NIST | Public-domain visuals and facts |
| Retraction Watch | "Science that turned out to be wrong" — underused, very shareable |
| Practical Engineering, Asianometry | Infrastructure and semiconductors, absent from IG |

**Batch-produce 30 of these in one sitting.** Target: never fewer than 15 approved evergreen posts in the queue.

`.claude/agents/evergreen-scout.md` is the intake for this tier: given a topic
family, it mines the sources above into a ranked shortlist of candidates —
each with a real source, a colorway, and a "why it matters" / "the catch"
angle — scored on the same four axes as `score.py`. It stops at the idea; a
person picks from the list and runs it through the normal draft → fact-check →
gate path. It never writes to `posts/` or drafts slide copy.

### Aggregation — do it in code, not with a service

Feedly Pro+ with Leo AI and Inoreader Pro are the convenient options, but both are **paid**. On a zero budget, skip them entirely: `feedparser` in Python does the same ingestion, and the LLM scoring layer (Layer 2) does the same filtering, better and for free.

- **RSSHub** — free and self-hostable; generates RSS for sources that killed theirs. Public instances exist but are rate-limited and unreliable; self-host if you need it.
- **NewsAPI / GNews / Currents** — free tiers exist but several prohibit production use on the free plan. Read the terms before depending on them. Not needed given Tiers 1–5.

### Not yet available: EurekAlert!

Embargoed access is reserved for people whose primary occupation is journalism at accredited outlets, working on daily/weekly/monthly deadlines. Applicants need **at least three months of published content consisting primarily of original journalistic reporting on science topics**; opinion-based blogs and new media outlets are not eligible. Registrants must digitally sign an embargo agreement.

A new Instagram page does not qualify, and this is a credentialing barrier rather than a paywall — there is no workaround. **Revisit at month 6+** once there is a body of original work. AlphaGalileo has similar requirements.

---

## 4. Tool stack — $0/month

| Layer | Free tool | Notes |
|---|---|---|
| Orchestration | **GitHub Actions** (cron for a Python script) | Unlimited minutes on public repos; 2,000 min/month private |
| Orchestration (alt) | **n8n self-hosted on Oracle Cloud Always Free** | 4 ARM cores + 24GB RAM, permanent, not a trial. Use if the visual editor is worth the setup. |
| Database / queue | **Google Sheets** (~10M cells) or **Supabase free** (500MB Postgres) | |
| Feed ingestion | **`feedparser`** in Python | No service needed |
| LLM scoring | **Gemini API free tier** (Flash) or **Groq free tier** | High volume, low stakes |
| Drafting | Free-tier LLM for routine posts; **this Claude project** for Breakdowns | |
| Image rendering | **Playwright → PNG** | Free and open source |
| Fonts / icons | **Google Fonts**, **Lucide** or **Tabler** | Free, self-hostable |
| Link in bio / archive | **GitHub Pages** | Free and unlimited on public repos; built and deployed by Actions |
| Image hosting | **GitHub Pages** or **Cloudflare R2 free tier** | Only needed for Graph API path |
| Design | **Figma free tier**, Canva free (manual only) | |
| Reels / video | **CapCut free**, **DaVinci Resolve free** | |
| Publishing | **Meta Business Suite Planner** | Free, first-party, carousels supported, no post cap |
| Analytics | **Instagram Insights** + Google Sheet | |
| Version control | **GitHub free** | Private repos included |

**Total: $0/month.**

### Free-tier edges to plan around

These are real limits, not obstacles to route around — knowing them up front prevents building on sand.

- **Airtable free caps at 1,000 records per base.** With ~40 feeds ingesting every 2 hours, that fills in roughly a week. This is why the stack uses Google Sheets or Supabase instead.
- **Gemini free tier is rate-limited** (roughly 15 requests/minute on Flash). Fine for scoring a few hundred items — batch the calls with a sleep between them rather than firing in parallel.
- **GitHub Actions scheduled runs can be delayed 10–30 minutes** during peak load on the free tier, and GitHub disables scheduled workflows after 60 days of repository inactivity. A monthly commit resets the clock. Neither matters for a 2-hour ingest cycle.
- **Canva Bulk Create is Pro-only.** Not worth working around; HTML→PNG is better output at zero cost.
- **Buffer free caps queued posts (~10) and Later free caps monthly posts (~30).** Meta Business Suite has neither cap, which is why it is Route A.
- **The X/Twitter API has no usable free read tier.** Bluesky replaces it and is genuinely better for science.

---

## 5. Design system

Locked before any automation, because everything downstream depends on it.

- **Canvas:** 1080×1350 (4:5 portrait — maximum feed real estate)
- **Type:** one display face for hooks, one highly legible sans for body, both from Google Fonts. Hook text must be readable as a thumbnail.
- **Color:** a set of field hues that rotate per post by topic family, over a constant neutral and near-black. What makes the grid recognizable is *not* a fixed sequence of colors — it is the `--ink` outline frame, the type, and the slide rhythm (cream rest slide, dark "catch" slide, matching first and last slides), all of which hold while the hues change. See the colorway table in `CLAUDE.md`.
- **Fixed elements:** @gummietech wordmark, same position every slide; slide-position indicator; source line on the final slide.
- **Rule:** if a slide has more than 25 words, it is two slides.

Design the template in Figma's free tier if it helps to see it, then translate to HTML/CSS — the HTML file is the production asset, not the Figma file.

*Direction chosen: playful/bright. Field hues vary per post to suit the subject; the ink frame and type carry the consistency.*

---

## 6. Captions, hashtags, discoverability

Hashtags matter far less than they used to — Instagram removed hashtag following and now leans on search keywords and content understanding.

- **First line = SEO.** Put the actual searchable terms in it: "quantum computing," "fusion reactor," "humanoid robot." Instagram indexes caption text.
- **3–5 hashtags maximum**, mixed: one broad (#technology), two niche (#quantumcomputing #materialsscience), one branded (#gummietech).
- **One link, and it is the archive.** `https://kemval.github.io/gummietechContent/` — newest post first, so the bio link always lands on what was posted today. A custom domain would cost ~$12/year and is the only thing in this plan that would break the $0 constraint; the default URL is fine until it isn't.
- **Always write alt text.** Accessibility win and a ranking signal. Already in the JSON schema.
- **End every caption with a question.** Comments are the strongest early-stage signal.
- **Reply to every comment in the first hour.** Non-negotiable, non-automatable.

---

## 7. Guardrails

These override efficiency, always.

1. **The human approval gate stays.** No post publishes without a person reading it.
2. **Preprints get labeled on-slide:** "Preprint — not yet peer-reviewed." A finding that fails to replicate after being posted as fact costs the credibility the whole account depends on. The transparency itself becomes a reason people trust @gummietech over pages that skip it.
3. **Attribution is a required field.** Turning someone's 3,000-word Substack essay into a carousel without credit is an IP problem and a fast way to make enemies in exactly the community whose support matters most. Use sources for the *idea and the understanding*; write every slide in original words; put "via @author" on the final slide and a link in the caption. Tag them — writers routinely reshare posts that credit them well, which is free reach from an audience that already cares.
4. **No fabricated numbers, dates, quotes, or study details.** If it isn't in the source, it doesn't go on the slide. Layer 3b checks this claim by claim against the fetched source; a claim it could not verify is held, not published.
5. **Never claim certainty the source doesn't have.** "Suggests," "early results indicate," "in mice" — keep the hedges the researchers used.
6. **Distinguish demo from product.** A lab demo is not a shipping capability.
7. **Free does not mean unverified.** A tool being on the free stack is not a guarantee it still is — check current terms before building a dependency on any free tier, and prefer open-source or first-party tools, which are least likely to change under you.

### What stays manual, permanently

Automate research, drafting, and design. **Never** automate: the approval gate, comment replies, DMs, or Stories. Stories are where followers become fans, and they need to sound like a person.

---

## 8. 30-day rollout

**Week 1 — Manual.** Post 7 days by hand using the 5-slide template. No automation. Find the voice, prove the format. Convert the account to Professional and link a Facebook Page (required for Business Suite scheduling). Decide the brand direction.

**Week 2 — Ingest + score.** Create the GitHub repo. Write the Python ingest script with ~40 feeds across Tiers 1–5 writing to Google Sheets. Add free-tier LLM scoring. Schedule it as a GitHub Action every 2 hours. Still writing and designing manually, but now opening a ranked list each morning instead of hunting.

**Week 3 — Auto-draft + auto-design.** Add the JSON drafting step and the Playwright PNG renderer. Morning becomes: review 5 candidates → approve 1 → edit copy → render. **Target: 20 minutes/day.** Batch-produce 30 evergreen posts.

**Week 4 — Publish + measure.** Schedule approved posts through Meta Business Suite (~5 min/day). Start the metrics sheet tracking saves and shares per post from Instagram Insights. After 30 posts, cut the weakest format and double the winner.

**Month 2+.** Consider the Graph API only if manual scheduling has become the real bottleneck. Begin building the original-reporting body of work that could eventually qualify for EurekAlert!.

---

## 9. Success metrics

| Metric | Why | Target by day 30 |
|---|---|---|
| **Saves per post** | Primary growth driver | Rising trend |
| **Shares per post** | Secondary growth driver | Rising trend |
| Follower growth rate | Lagging indicator | — |
| Comments in first hour | Early algorithmic signal | ≥5 |
| Time from source → published | Pipeline health | <45 min for a Drop |
| Days missed | Consistency | 0 |
| Evergreen queue depth | Buffer health | ≥15 approved |
| Monthly spend | Constraint | $0 |

Explicitly **not** a primary metric: likes.

---

## 10. Open decisions

- [x] Brand direction: playful/bright, with field hues rotating per post by topic (see §5)
- [ ] Instagram account converted to Professional + linked Facebook Page
- [ ] Orchestration: GitHub Actions (simpler) vs. n8n on Oracle Cloud (visual editor)
- [ ] Database: Google Sheets (simpler) vs. Supabase (scales better)
- [ ] Posting time locked (test 3 slots, pick by save rate)
- [ ] Reels: in scope for month 1, or defer to month 2?
- [ ] Spanish-language variant — Costa Rica base is an underserved-market advantage worth considering
