# The Build — episode list

The Build is the conversion pillar (§1 of `gummietech_content_system.md`):
a 30–60s reel, recorded, cut and captioned by a person. Nothing in `src/`
makes one. This file is a list to film from.

Every episode below is a real bug this pipeline hit, taken from a dated
post-mortem in `CLAUDE.md`. Every number in it is measured, not recalled.
That is the positioning: most tech pages are run by communicators, and this
one is run by someone whose code breaks and who shows the fix.

**The shape, every time** (project instructions §The Build): cover frame in
Drop hook styling → the problem → fast-cut screen recording of real work →
the result running → close with the number. The caption carries the stack,
because that is where a prospective client reads competence.

**Before filming**, check the number is still what `CLAUDE.md` says. Several
of these were measured once, on one day.

---

### 1 · The cron that runs late

- **Cover** — "I asked GitHub for a run every 15 minutes. I got one every two hours."
- **Problem** — `publish.yml` asks for `*/15`; on 2026-09-20 it ran 8 times in 19.5 hours. The daily draft ran 5 of 5 times, but 3h38m–5h55m late.
- **Record** — the Actions run list for `publish.yml` with its timestamps; `daily.yml`'s four-firing cron line and its `gate` job.
- **End on** — "Ask earlier, not more often: four firings a day, one gate."
- **Pairs with** — `posts/2026-09-28-the-cron-that-runs-late.json`, the carousel of the same story. Post the reel the same week and let each link to the other.

### 2 · My AI credited the wrong scientist

- **Cover** — "My pipeline credited a 2026 discovery to a paper from 2014."
- **Problem** — `resolve_paper` took the first DOI on a news page, and that page's related-stories rail carried another paper's DOI (Wegst et al., 2014; post-mortem 2026-09-18).
- **Record** — the news page with the rail highlighted; `DOI_CUES` in `src/draft.py`; the test in `tests/test_draft.py` that pins it.
- **End on** — "Now it reads the journal reference first. The rail is last."

### 3 · Two free AIs covering for each other

- **Cover** — "The free AI tier killed half my runs, so I made two of them cover for each other."
- **Problem** — Gemini's shared free tier returned 503s, which took out 4 of 8 scheduled ingests on 14–15 Sep 2026.
- **Record** — a failed run log with the 503s; `llm.py`'s switch message; a green run after the change.
- **End on** — "Only overload fails over. A spent quota still stops the run — hiding it would spend tomorrow's budget."

### 4 · Nine lost replies

- **Cover** — "I lost nine of my own analytics replies in a single day."
- **Problem** — the bot asks for saves/shares/visits; nine answers typed as plain messages instead of replies named no post, and all nine were dropped (2026-09-21).
- **Record** — the chat showing the unreplied numbers; then the same ask with Telegram's ForceReply opening the reply box by itself.
- **End on** — "The fix wasn't a better sentence. It was making the keyboard do it."

### 5 · The feed that was live and dead

- **Cover** — "My feed checker said this source was fine. It hadn't published in a year."
- **Problem** — SemiAnalysis answered 200 with 10 entries, the newest from Sep 2025. Every "did entries come back?" check said yes (2026-09-22).
- **Record** — `python src/verify_feeds.py -v` showing the age column; the stale mark.
- **End on** — "Live and finished look the same until you measure the newest entry's age."

### 6 · Three amber posts in a row

- **Cover** — "Every rule worked, and my grid still went orange three days running."
- **Problem** — materials, biohybrid robotics and thermodynamics all mapped to `ember` (2026-09-18 to 09-20).
- **Record** — the Instagram grid; `render.vary()`; the grid after.
- **End on** — "Topic picks the colour. The post before it gets a veto."

### 7 · The fact-checker held by its own summary

- **Cover** — "My fact-checker blocked a post for finding nothing wrong."
- **Problem** — the report ended "0 BLOCK" and the gate matched the word BLOCK.
- **Record** — the held Telegram message; the `FACT-CHECK · PASS` verdict line the gate reads now.
- **End on** — "A gate that holds clean posts teaches you to ignore the gate."

### 8 · Perfect pipeline, zero saves

- **Cover** — "I built a fact-checked, self-monitoring content pipeline. It has zero saves."
- **Problem** — 22 posts by 2026-09-27: 0 saves in total, about one share each. The engineering was never the bottleneck.
- **Record** — `python src/learn.py`; the hook comparison (a headline hook against "The two tidal bulges you were taught in school don't exist").
- **End on** — what changed: three hooks per draft, chosen at the gate. Film the follow-up once `learn.py` has numbers for it.

### 9 · A $0 stack, with the limits named

- **Cover** — "Everything this account runs on costs $0 a month. Here's what that actually costs."
- **Problem** — free tiers have caps: the Gemini daily cap, GitHub's shed crons, no Instagram API without app review.
- **Record** — the Stack table in `CLAUDE.md`; a 429; the Telegram gate.
- **End on** — "Free is a design constraint, not a discount."

### 10 · Link previews from the slides themselves

- **Cover** — "Nobody tapped my links, because they showed nothing."
- **Problem** — the archive had no preview tags, so a link pasted into a DM was bare text.
- **Record** — a pasted link before and after; `site.py` rendering each cover through the same page `render.py` screenshots.
- **End on** — "Same renderer, so the preview is the post."
