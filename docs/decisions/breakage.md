# When something breaks

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## When something breaks

Two pieces, because the failures divide in two.

**`check.yml` runs on every push** and exercises the half of the pipeline
that needs no secret, no network and no LLM call: every module in `src/` is
loaded by path, `posts/era.json` is rendered and proofed, the whole archive is
built, and `translate.py --check` confirms no post's Spanish is older than its
English. A second job installs *only* the two packages `publish.yml` installs
and loads `telegram.py` under them — that list is maintained by hand against
`telegram.py`'s imports, and the day it fell behind, `confirm` died at module
load on every poll for a day.

That job is deliberately not a test suite: it asks whether the pipeline still
runs end to end, and it catches the class of break that used to surface at
06:17 — a missing dependency, an import cycle, a template that stops
rendering, Spanish left behind by a correction.

**The test suite is a third job**, `tests`, over `tests/` with pytest. It asks
a different question — does this function still do what the post-mortem says
it must — which is why it is a job of its own rather than more steps in
`smoke`: a red there names a stage, a red here names a behaviour. Run it with
`python -m pytest`; `requirements-dev.txt` pulls in `requirements.txt` and
adds pytest, and nothing in it touches the network, an LLM or a browser.

Every test in it is a case this repository has already got wrong once. That
is the entry criterion, and it is what keeps the suite from growing into
something nobody reads:

- `resolve_paper` walking into a paper's own reference list and crediting
  Wegst et al. (2014) on a 2026 story (2026-09-18).
- A fact-check held by its own closing summary of having found nothing.
- Spanish reported as up to date on fifteen posts nothing could check.
- `--evergreen` re-drafting the tides post, still #1 in the queue.
- A metrics reply silently dropped because the mark moved behind an emoji.
- Five of a Breakdown's eight slides sent to the gate, reported as five.
- Every `era*.json` fixture reported as clashing with the newest real draft,
  because a path outside `post_order()` is read as arriving at its end.
- Nine metrics answers typed into the chat instead of replied with, dropped
  in silence, while `learn.py` reported the asks as simply unanswered.

What none of the three jobs can catch, so nobody mistakes green for safe:
anything that needs a real run — Telegram's message cap, a checkout resolving
to the wrong SHA, a provider's 429. Green is not safe, it is only "nothing
obvious".

Note that commits pushed by the workflows themselves use `GITHUB_TOKEN`, which
by design does not trigger other workflows, so a bot-committed draft is not
checked. A hand correction at the gate is pushed by a person, and is.

**A failed run says so in Telegram.** `.github/actions/notify-failure` is a
composite action called from an `if: failure()` step at the end of every
scheduled workflow, and it posts the run URL to the same chat the gate uses.
It lives in one file for the reason `review.yml` does. Two details:

- **It speaks on every failed run, `publish.yml`'s poll included.** It used
  to take an `hourly: 'true'` from `publish.yml`, which silenced any run
  starting after minute 15 — the throttle that kept a quarter-hourly cron
  from sending 96 identical messages a day and teaching a person to mute the
  bot. That check was a proxy for "the first poll of the hour", and it was
  only ever equivalent while the polls landed on :00/:15/:30/:45. At the
  cadence the free tier actually delivers (above) the runs land at whatever
  minute they like, and six of the eight measured would have been silenced —
  a one-off failure as readily as a persistent one. An action that exists
  because failures were invisible cannot drop three alerts in four, and the
  spam it insured against is now capped by the platform at about eight
  messages a day. A stateless step cannot tell a repeat from a first
  sighting, so the throttle is gone rather than rebuilt.
- **Missing credentials are a no-op, not a second failure.** The point is to
  make a break visible, never to add one on top of it.
