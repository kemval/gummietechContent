# Watching the pipeline

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## Watching the pipeline

`notify-failure` speaks for a run that started and broke. `watch.yml` is what
speaks for one that never started, and it can only do that by being a
different run: `src/watch.py`, once a day, asking what the pipeline should
have left behind and reporting what is not there. It sends one message or
none.

```bash
python src/watch.py                  # print the report
python src/watch.py --send           # ...and send it if it is not a PASS
python src/watch.py --skip-feeds     # skip the slow network sweep
```

Twelve checks, each answerable from a file, a sheet cell or a Telegram update —
so none of it needs a model and none of it spends a quota:

| check | the question |
|---|---|
| `cadence` | the last drafting day that **ended** has its post — a Drop Mon/Wed/Fri, the week's Signal on Saturday |
| `glossary` | from Wednesday on — Tuesday is its day — this week has its Glossary term, or the Cheat Sheet in its place |
| `breakdown` | from Friday on — Thursday is its day — this week has a Breakdown |
| `subject` | yesterday's Drop, and every item of yesterday's Signal, was tech — not a science fallback because the tech pool was dry |
| `gate` | every tap in Telegram's 24h window reached `published_at` |
| `metrics` | every answered ask was written down, no answer arrived unreplied, and old asks were answered |
| `colour` | no two neighbouring posts share a field |
| `buffer` | drafts are not silently piling up at the gate |
| `feeds` | every feed still returns entries, and still publishes them |
| `queue` | rows are still arriving, and candidates are still scored |
| `structure` | `check.yml`, whose result the workflow hands over |
| `fact-check` | it is configured at all |

Six things hold it together, and every one of them is a rule about not crying
wolf — a watcher nobody reads is worse than none:

- **It only asks about obligations that have already come due.** A daily cron
  arrives 3–6 hours late, so `last_draft_day()` walks back from *yesterday*,
  never from today. A day that has ended owes its post unconditionally; today
  might just be running behind. This is why `watch.yml` asks once rather than
  copying `daily.yml`'s four firings: that shape exists to land near an hour,
  and this has no hour to land near.
- **A finding nobody can act on is a note, not a finding.** Notes print but
  do not move the verdict, and only a non-`PASS` verdict sends. A colour run
  that is already published is history — there is nothing to re-render and no
  tap to withhold — so it stays visible in a hand run and silent in the chat.
  The same reasoning as a clean fact-check that must not hold a post. It is
  also why `glossary` and `breakdown` ask only about the current week and
  only from the day after theirs (`BY_HAND_WEEKLY`): a week that already ended without one is history, and saying so
  every day until the next Monday would be nagging.
- **Findings exit 0.** The message *is* the report. A non-zero exit would
  make `notify-failure` send a second message about the same thing. Only an
  unexpected failure exits non-zero, and that genuinely is a broken run.
- **Every check degrades rather than dying.** `open_sheet()` exits with
  instructions when the credentials are missing; `watch.py` catches that and
  reports the queue as unchecked. A watcher that dies on one unconfigured
  check reports nothing about the eight that are fine.
- **It reads `getUpdates` without an offset, like `confirm` does.** That
  leaves the cursor alone, so reading the same 24-hour window from a second
  process cannot take a tap away from the poll meant to act on it.
- **`check.yml` runs as a called workflow, not as copied steps.** It gained
  `workflow_call` for this. The point is the hole `check.yml` documents in
  itself: bot commits use `GITHUB_TOKEN` and do not trigger its `push`, so
  the three drafts a week the bot writes were never exercised. Its result is
  passed to `watch.py` with `--structure` so a red check is a line in the
  message rather than an ✗ on a run nobody is watching.

**`watch.yml` installs `requirements.txt` but not the browsers.** `watch.py`
imports `render.py` for `post_order()` and `vary()`, and `render.py` imports
Playwright at module level — but the pip package imports fine without
`playwright install`, and nothing here ever opens a page.

Three things it cannot do, which matter as much as what it can:

- **It cannot prove it ran.** It is on the same scheduler that sheds, so its
  silence means "nothing to report" *or* "I did not run", and nothing
  distinguishes them. Making its absence visible costs a message a week; that
  trade is open, not made. Do not "fix" it by tightening the cron.
- **Telegram does not timestamp a tap.** `callback_query` carries no date, so
  a tap made shortly before a run is indistinguishable from one the poll
  lost. That is why an unrecorded tap is a FIX that says the poll may still
  be pending — a genuinely lost tap reports every day until it is fixed, and
  that repetition is the signal.
- **It does not measure how late a cron was.** The Actions API would give
  that and it would change nothing, since GitHub cannot be asked for less
  delay. So `watch.yml` asks for no `actions:` permission at all.
