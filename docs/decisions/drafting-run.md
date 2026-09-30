# The drafting run and the gate

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## The drafting run

`daily.yml` on Monday, Wednesday and Friday — the three Drops `docs` §1
fixes the cadence at — drafts the top-scoring queued row, translates it and
commits the JSON, then calls `review.yml`, which fact-checks, renders, proofs
and sends to Telegram. It asks for four firings a day and drafts on one: the
cron is delivered hours late and unpredictably so (above), so the four are
one request repeated, and the `gate` job stands in front of the draft to
answer "has today already been drafted?" off the post's filename. A bare
`workflow_dispatch` is held to that too — on 2026-09-21 a hand dispatch sent
one minute after a six-hours-late cron had started produced a second
unwanted draft, because `concurrency` queues a run rather than dropping it.
The override is the `force` input, explicit for the same reason `--row` is:
naming a candidate by hand is an override, and a bare dispatch names nothing.

It ran daily until 2026-09-19 against a three-a-week pillar, and the four
surplus drafts a week each spent a draft call, a translate call, a
`fact-check` run on the Claude quota and a message in the chat, while the
buffer of undated drafts grew with nothing deciding how deep it should get.
`publish.yml` polls for the reply on a 15-minute cron that the free tier
actually delivers about every two hours. Between them sits a person, doing
what only a person can:

```
daily.yml ─ draft · translate · commit ──┐
recheck.yml ─ re-run the checks ─────────┤─→ review.yml ─ fact-check · render
fix.yml ─ apply the report · commit ─────┘                · proof · send
                                                                   │
                                                                   ↓
                                                               Telegram
                                                                   │
                          you read the reports, post the carousel  │
                          to Instagram, tap the button             │
                                                                   ↓
publish.yml ─ published_at · commit · dispatch site.yml ─→ the archive
```

`review.yml` is a `workflow_call` reusable workflow rather than steps inside
`daily.yml`, because two callers need it: the drafting run, and `recheck.yml`
when a review breaks rather than finds something. The gate that withholds the
button therefore lives in one place — a second copy is a second place to
forget to hold a post. It never drafts, never commits and never dates a post.
The caller commits first, which is what lets `review.yml` read the post in its
own checkout, and what lets `recheck.yml` find it again days later.

`recheck.yml` exists because re-running `daily.yml` is not the way back from a
held post: `draft.py` with no argument takes the *next* queued row, so a
re-run would skip the held post and spend tomorrow's story. Dispatched with a
blank `post` input it re-reviews the one awaiting approval.

Which post that is used to mean the newest dated file in `posts/` without
`published_at`, and the cadence decision made that answer wrong: at 3×/week,
drafted ahead and buffered from the evergreen queue, several undated posts are
the normal state rather than the broken one, and the newest of them is a
buffered draft rather than the post a person is looking at. So the question is
no longer "which draft is newest" but "which post is the person looking at",
and the chat answers it — `review.yml` uploads a `reports-<stem>` artifact for
every post it sends, so the newest surviving one names the post the gate last
spoke about, which is the post whose message carries the buttons. It needs
`actions: read` to ask; without a token it falls back to the old pick, which
is right only while there is one undated draft. The date-prefix filter in that
fallback is load-bearing rather than tidy: the `posts/era*.json` fixtures have
neither a prefix nor a `published_at`, and sort after every real draft, so
unfiltered one of them would be picked every time. That picking lives in
`.github/actions/resolve-post`, because `fix.yml` has to answer "which post is
held" identically or the two ways back repair different posts.

`fix.yml` is the other way back, and the two divide by *why* a post is held.
`recheck.yml` runs the same review again, which is the answer when the check
broke. `fix.yml` is the answer when the check was right: it fetches the
`reports-<stem>` artifact the holding run uploaded — the report the person
actually read, not a fresh one — applies it, re-translates, commits, and calls
`review.yml`. It is dispatched by tap and never scheduled, because some BLOCKs
are the checker being wrong rather than the post, and a Claude run spent on
every one of those burns the quota the checking itself needs. It never dates a
post: the corrected slides come back to the chat for approval exactly like the
first draft. Three limits hold it to repairing rather than rewriting:

- **It applies, it does not compose.** Where the report suggests replacement
  wording it uses that; where it does not, the unsupported claim comes out and
  the sentence runs shorter. The failure being repaired is a model writing a
  caveat the paper does not state, and a repair free to write a new one is not
  a repair. A finding that cannot be fixed by editing — the wrong paper, a
  post about something the source does not say — changes nothing and says why,
  because a post that needs re-drafting is not a post to patch.
- **A guard step on the diff, not the prompt, is what enforces that.** After
  the applier runs, `git diff --name-only` must name exactly the one post and
  the JSON must still have no `published_at`, or the run fails having
  committed nothing. The `settings` block is the contract; the diff is the
  proof.
- **It never grades itself.** The fact-check that decides whether the post is
  now true is the one `review.yml` runs afterwards, in a session that never
  saw the applier.

**A cover line is swapped from the chat too.** Every Drop drafted since
2026-09-27 carries three hooks, and its message carries a **🔀 Swap the hook**
link to `hook.yml` on both keyboards, held or not. Which hook stops a thumb is
a judgement about the post, not about whether a check passed. It is a link
for `workflow_url()`'s reason, and it spends no Claude quota of its own: only
the review it hands off to does.

**A reel is asked for from the chat, and recorded by the same poll.** The ✅
`confirm` replies with on a Drop carries a **Make a reel** link to
`reel.yml` — a link for `workflow_url()`'s reason below. `send-reel` puts the
MP4 and its cover in the chat as documents with a `reel:` button, which
writes `reel: {published_at}` into the post rather than touching
`published_at`: the carousel was dated long before. Like `ser:`, it never
reports `published=true`, since `site.py` does not read the reel block.
`recorded()` is what knows which marker each prefix sets; `watch.py` asks it
too, so a lost reel tap is not mistaken for a recorded one.

`src/telegram.py` is both halves — `send` and `confirm` — because both are
the same boundary, and its docstring holds the API-level reasoning. The
constraints that shape it:

- **The slides go as documents, not photos.** `sendPhoto` re-encodes to JPEG
  and downscales past 1280px. The slides are flat colour fields behind a 10px
  border, which is what JPEG bands worst, and they are about to be recompressed
  again by Instagram. Never switch the media group to `photo` to get inline
  previews — Telegram previews a PNG document anyway.
- **How many slides it sends is discovered, not counted.** `rendered_slides()`
  globs `slide-*.png` and orders by the number, because how many slides a post
  has is the template's business here exactly as it is in `render.py`. A fixed
  `slide-1..5` list sent five of a Breakdown's eight and printed "sent 5
  slides", which puts a person one tap from approving a carousel they saw half
  of. A hole in the numbering sends nothing: that is a render that stopped
  partway. `sendMediaGroup` takes 2–10 items, so a format longer than ten goes
  in evened-out groups rather than 10 + a remainder Telegram would reject.
- **The post stem is the only state between the halves,** carried in the
  button's `callback_data` (64 bytes; `slugify` caps a stem at 51). That is
  why `daily.yml` commits the draft *before* sending: `confirm` finds the
  file by name on master.
- **`getUpdates` is called without an offset,** so every tap replays on every
  poll for 24 hours. `confirm` is idempotent against that — it skips a post
  that already has `published_at` — which is what lets it keep no cursor
  between runs. Do not add offset tracking; it would buy nothing and add a
  state file to lose.
- **`publish.yml` dispatches `site.yml` by name.** A push made with
  `GITHUB_TOKEN` does not fire another workflow's `push` trigger;
  `workflow_dispatch` is the documented exception. Removing that line makes
  the archive silently stop updating.
- **`publish.yml` installs `requests` alone,** not `requirements.txt` — it is
  the most frequently run workflow here, and `telegram.py` deliberately does
  not import `render.py`, which would drag in Playwright.

### Another story — rejecting a draft from the phone

A post can pass every check and still not be worth posting: the checks ask
whether it is *true* and *legible*, not whether it gives a follower anything.
The gate message links to `redraft.yml` as **Another story** on both
keyboards, for Drops and Signals (a Breakdown is written by hand, so there is
no "next one" to draft). The form takes an optional reason.

- **The draft is moved to `posts/rejected/`, not deleted.** `covered_papers()`
  reads that directory too, so the rejected paper does not return through a
  sibling feed's row — the whole failure `docs/decisions/dedup.md` is about.
  Every other reader of `posts/` globs `*.json` without recursing, so the
  move takes it out of the archive, `resolve-post`, `watch.py` and the daily
  gate at once, with no field for any of them to learn.
- **The sheet row is left alone.** It is already `drafted`, which keeps
  `pick_row()` off it.
- **The reason is kept for `learn.py`,** which lists rejections by `beat`: a
  story with no numbers leaves no other signal, and a beat that keeps being
  rejected is the one to take off `PRIORITY_BEATS`.
- A link, not a callback, for `workflow_url()`'s reason. It shares
  `daily.yml`'s concurrency group: both take a row and push to master.

### Both reviews gate the button

`telegram.py send --review FILE` carries each report into the message, and a
report containing `BLOCK` or `UNVERIFIED` withholds the approval button. That
is the gate: the ordinary tap that publishes is not offered on a held post.

What a hold cannot do is stop the carousel. Instagram is posted by hand,
outside all of this, so withholding every button protects nothing about the
account — it withholds only the *record*, and leaves a person who has already
posted with nowhere to say so except a hand edit to the JSON, which leaves no
trace that anything was overridden at all. So a held post carries three
buttons in place of the green one: **Apply the fixes**, **Re-run the checks**,
and **Posted anyway — record it**. The last dates the post as the green one
would; what
differs is that it carries `held:` rather than `pub:` in its `callback_data`,
so `confirm` knows it was an override and says so in the run log and in its
reply in the chat. A visible override is worth more than a gate that is only
technically unbroken — and the reports stay in the chat above it either way.

**Apply the fixes** is offered only when the *fact-check* is what held the
post. `fix.yml` applies a fact-check report and has nothing to say about a
layout `proof.py` measured and rejected, so offering it on a proof hold would
send a person to a workflow that reads the report, finds nothing it can act
on, and changes nothing.

- **`proof.py`** runs on every post and needs no credentials.
- **`fact-check`** runs as a Claude Code agent through
  `anthropics/claude-code-action`, authenticated with `CLAUDE_CODE_OAUTH_TOKEN`
  from `claude setup-token`. That bills the **Pro subscription, not the API**,
  so it stays inside the $0 rule — but it does draw on the same quota as
  interactive Claude Code sessions, which is why `--max-turns` is capped. The
  agent's read-only contract is held on the runner by a `settings` block that
  allows `Write(/tmp/**)` and denies `posts/` and `src/` outright.
- **No token, no gate change.** With `CLAUDE_CODE_OAUTH_TOKEN` unset the step
  is skipped and the stand-in report says so *without* the gate words, so the
  button behaves as it did before fact-checking existed. A step that was
  configured and then failed writes `UNVERIFIED` instead and does hold the
  post — a check that broke is an unknown, and `fact-check.md` is explicit
  that an unverifiable post is a hold, not a pass.

**The gate reads a verdict line, not the prose.** Both checkers state their
finding on the report's first line — `PROOF · PASS`, `FACT-CHECK · PASS` — and
`BLOCK` there is what withholds the button. The first real fact-check to reach
this gate closed with "Safe to render — 0 BLOCK, 0 required FIX" and was held
by its own summary of having found nothing; a clean post held every day is
worse than no gate, because it teaches a person to tap the override without
reading.

A report with no verdict line still falls back to `GATE_RE`, which matches
`BLOCK` and `UNVERIFIED` case-sensitively on word boundaries. That is what
holds the stand-in review.yml writes when a configured fact-check produces
nothing, and what leaves the button alone for the "not configured" one, which
contains neither word.

Of those three buttons, only one is a real button. **Apply the fixes** and
**Re-run the checks** are **links** to `fix.yml` and `recheck.yml`, so the way
back from either kind of hold is one tap from the chat it arrived in. They are
links, and not buttons that do the work, because
`getUpdates` has no offset: a callback tap would replay on every poll for 24
hours and re-dispatch the work every quarter of an hour — burning the Claude
quota whose exhaustion is the likeliest reason the post is held at all.
`confirm` survives that replay only because dating a post twice is a no-op,
and neither a re-check nor a repair has such a marker. `workflow_url()` builds
both from `GITHUB_SERVER_URL` and `GITHUB_REPOSITORY` rather than from
constants, so a local `send` offers neither — whoever ran it by hand is
already at a machine that
can re-run the checks.

A third link, **Record it now**, sits under every publish button — the green
one and the override alike — and points at `publish.yml`'s
`workflow_dispatch`. It exists because a publish tap cannot be answered when
it is made: `confirm` runs on the cron, so by the time it sees the tap the
callback id is long past the seconds Telegram allows a bot to answer in, and
the message edit that *is* the acknowledgement is a couple of hours away.
Nothing visibly happens in between, which reads exactly like a bot that has
stopped working rather than one that is asleep.

So the fix is in two halves, and the copy is the larger one. `waiting_note()`
says in the message, before the tap, that nothing will appear to happen, how
long that lasts, and what the end of it looks like — a person who knows the
silence is normal does not need it shortened. The link is for when they want
it shortened anyway: two taps runs the poll, and the tap lands in under a
minute. It is safe to tap early, twice, or with nothing tapped at all, for the
same reason every other poll is — `confirm` is idempotent and a tap replays
for 24 hours.

Nothing gates a **local** `send` with no `--review` flags — the message says
plainly that nothing checked the post, but the button still appears, because
a person sending by hand is already in the loop. A local send offers no
**Record it now** either, for `workflow_url()`'s reason above, and the
waiting note drops its last sentence rather than pointing at a link that is
not there.
