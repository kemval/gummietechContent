# Status-report pillar: mechanics

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## The status-report pillar

A second content stream beside the carousels: single 1080x1350 slides of
relatable-dev humour under a `STATUS REPORT #NN` eyebrow, one a day.
`series.yml` sends the next one to the same Telegram chat with its caption and
one button; `publish.yml`'s existing poll takes the tap back. Layer 5 applies
here exactly as it does to a Drop.

Its strategy, numbering contract, design tokens and what is built lives in
`docs/gummietech_status_reports.md` — read it when the task touches what gets
posted rather than how the sending runs. `python src/series.py` prints the
queue: what is next, what is missing an image, how many days of runway are
left, and whether the numbering has a hole or two neighbours share a module.

**It is not a `post_type`, and adding one would be the mistake.**
`formats.RECORD` requires `attribution`, `source_url` and `peer_reviewed` on
every record and `render.load_post()` refuses one without them — because a
post that cannot name its source must not ship. A status report has no source
to name. It also uses a different, locked design system (warm cream
`#F3EEE6`, Instrument Serif / Manrope / JetBrains Mono) that has nothing to do
with `templates/tokens.css`. So it gets `src/series.py`, a small stdlib-only
manifest module, and nothing in `src/` renders it.

**The slides are exported by hand.** They are designed on a Claude Design
canvas and exported to `series/images/` — that export is a click in a browser
and no workflow can do it. `.gitignore` blanket-ignores `*.png`, so
`!series/images/*.png` is what lets them be committed at all; delete that line
and `series.yml` silently finds no image and sends nothing.

Four things that are deliberate:

- **A third callback prefix, `ser:`.** It dates a record exactly as `pub:`
  does, so it looks like duplication. It is not: `confirm` reports
  `published=true` on `GITHUB_OUTPUT` and `publish.yml` dispatches `site.yml`
  on it, and `site.py` reads `posts/` and nothing else — so a report tap
  answered as `pub:` would rebuild the archive into byte-identical HTML every
  day it went out. The same shape as the metrics-comma bug: a write next to
  `published_at` claiming a publish that did not happen.
- **One poller, not two.** `getUpdates` is called without an offset, so every
  tap replays for 24 hours; a second polling workflow would see and answer the
  same taps. `confirm` handles both pillars, and `locate()` is the one lookup
  that finds a stem in either collection.
- **`sent_at` is not `published_at`.** Sending writes nothing else, so
  `series.yml`'s gate has no filename to test the way `daily.yml` tests
  `posts/<today>-*.json`. `sent_at` is that marker — and "the bot showed it to
  me" and "I put it on Instagram" are different facts, hours apart.
- **A report with no image yet is not a failed run.** The queue runs ahead of
  the export, so `send-series` says what is missing in the chat and exits 0.
  Failing would fire `notify-failure` every day until someone sat down at a
  computer, which teaches a person to ignore the bot. It does not skip ahead
  to the next report that *is* ready: the numbering is public, and a gap reads
  as posts gone missing.

`python src/learn.py --series` is the Layer 7 half, grouped by `module` and
`eyebrow` rather than `post_type`/`colorway`/`domain` — what varies in this
pillar is the layout the slide is built from, and "which module earns another
ten" is §8's format decision one pillar down.

### Sending a different one today

The report message links to `series.yml` as **Send a different one today**;
ticking `swap` there runs `telegram.py send-series --swap`. The number is
drawn into the slide, so today's report cannot be skipped (a public gap) and
the next numbered one cannot stand in for it (the skip `next_unsent()`
refuses). An **unnumbered** report has no place in the run, so it goes out
instead, and today's report loses its `sent_at` — it is `next_unsent()` again
and goes out tomorrow. With no unnumbered report ready, the swap says so in
the chat and changes nothing. A report already posted is never taken back.

The swapped-out message keeps its ✅, and a tap replays for 24 hours — past
the moment the report is re-sent. So `confirm` ignores a `ser:` tap whose
report has no `sent_at`, or whose message is from an earlier day than
`sent_at` (`stale_series_tap()`): a live button's message is always sent on
its report's `sent_at` day.
