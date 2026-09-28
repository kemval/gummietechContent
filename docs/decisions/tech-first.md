# Tech-first selection

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**The account is tech-first, and the score is not where that lives.**
AI, software, automation, ML and robotics come first; science fills in.
Taking the single top score never got there — measured on 2026-09-27 over
8,095 rows, the `ai` feeds averaged 4.88 against biology's 6.74 and 1 of 195
reached the 8.75 where the queue's top starts, so September shipped almost no
AI with 777 tech candidates queued. So `score.py` names each item's `beat`
in the same call (a column appended to the sheet — `topic` is the *feed's*,
and Phys.org carries AI while Tech Xplore carries batteries), and
`draft.pick_row()` takes the best row whose beat is in `PRIORITY_BEATS`
before any other. A row scored before `beat` existed falls back to its feed's
topic rather than being re-scored, which would spend days of quota. A Signal
inherits the rule, since it walks `pick_row` five times; `--row`, `--url` and
`--evergreen` are overrides and ignore it. Do not move the preference into
the score: a topic bonus would make the number stop meaning "worth posting".
