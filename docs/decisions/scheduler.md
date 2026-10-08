# The GitHub Actions scheduler

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**GitHub Actions on the free tier** delays scheduled runs by 10–30 minutes at
peak and disables scheduled workflows after 60 days of repo inactivity.
Neither matters for a 2-hour cycle, but do not build anything that assumes
punctual execution.

**It also does not honour a high-frequency cron, and a cron is a request
rather than a promise.** `publish.yml` asks for `*/15 * * * *` and gets
roughly one run every two hours: measured on 2026-09-20, eight runs across
19.5 hours — 06:04, 10:52, 14:01, 17:15, 19:24, 21:31, 23:30, 01:36 UTC.
Read every "every 15 minutes" in this file as "a handful of times a day, on
GitHub's terms". What that changes: a tap is recorded within a couple of
hours rather than minutes, and anything rate-limited to one per poll drains
about eight times slower than the cron suggests. What it does not change:
nothing here is correctness-dependent on the interval — `confirm` is
idempotent, and a tap replays for 24 hours whatever the cadence.

**A once-a-day cron is not shed, it is delivered hours late — a different
failure with a different fix.** `daily.yml` has been honoured every single
time it asked (5/5 as of 2026-09-21) and never once near the minute it asked
for: a 12:17 UTC cron ran at 17:04, 17:04, 16:29, 15:55 and 18:12, between
3h38m and 5h55m late. `created_at` equals `run_started_at` on all five, so
this is the scheduler firing late rather than a run queueing behind a busy
runner. Do not confuse the two shapes: a `*/15` cron loses most of its
firings and keeps its punctuality, a daily cron keeps all of them and loses
its hour.

What it cost: on 2026-09-21 the Monday Drop reached Telegram at 12:15 local
against a comment promising 06:30, which reads as a broken pipeline rather
than a late one — nothing had failed, and no alert fires for a run that
simply has not started yet. `notify-failure` speaks for broken runs; it
cannot speak for absent ones, because a run that has not been created has no
runner to speak from. Nothing did, until `watch.yml` — a *different* run,
once a day, looking backwards at what the pipeline left behind. See
**Watching the pipeline**.

Since you cannot ask GitHub for less delay, only for an earlier hour,
`daily.yml` asks four times — `17 6,8,10,12 * * 1,3,5` — and its `gate` job
makes every firing after the first a no-op by asking whether `posts/` already
holds a post dated today. The worst case is the old behaviour; the best case
is a message waiting before the day starts. Any workflow that must land near
a particular hour needs the same shape. Do not tighten the interval instead:
that is the `*/15` mistake, and it buys shedding on top of lateness.

## Late crons collide on master

Lateness bunches runs together, and seven workflows commit to master
(daily, weekly, series, publish, fix, hook, redraft). 2026-10-08:
`series.yml` sent status report #16 at 13:25:18 UTC and lost its push to
`weekly.yml`'s Breakdown commit a second earlier — `cannot lock ref
'refs/heads/master'`. A `git pull --rebase && git push` had run, and was
not enough: the other commit landed between the two. The report was in the
chat but its `sent_at` was not on master, so the next run would have sent
#16 again and `confirm` ignored its tap as stale. `sent_at` was added by hand.

Every commit now goes out through `.github/actions/push`: pull with rebase,
push, and on a loss abort any rebase, wait 5–25s with jitter, and try again,
five times. A commit that still cannot land fails the run, and
`notify-failure` says so. Never put a bare `git push` back in a workflow.
