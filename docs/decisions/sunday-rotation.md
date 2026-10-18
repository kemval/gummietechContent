# Sunday: "Can I run it?" and the rotation

Added 2026-10-18. The reach plan of 2026-10-12 had four phases. Phases 1–3
were PRs #34–#36. Phase 4, a post every Sunday that rotates through four
new formats, was planned and never built. On 2026-10-18 Sunday sent the
status report alone, and the owner remembered there had been a plan but
not what it was. It was found again in a session transcript. Its first
format is this one.

## What it is

`post_type: "reference"`: a cheat sheet about one model, with a catch. It
shares `sheet.html`, which adds the dark slide when the record has
`the_catch`. It is written by Claude in `weekly.yml` on Sunday, as the
term and the Breakdown are, and reviewed by `review.yml` like any post.

## Why each rule

- **Its own post_type, not `sheet` with a flag.** `sheet` has
  `catch=False`, and `proof.check_rhythm()` reads that from the table. A
  sheet also fills the glossary's Tuesday slot (`KINDS["glossary"].slot`),
  so a Sunday sheet would have counted toward the next week's Tuesday.
  `learn.py` groups by post_type, so its saves can be compared.
- **Built on a published post, not a queue row.** The owner asked for the
  week's fresh launch. The fresh launches reach this account as Drops and,
  mostly, as Signal items, and those have already passed a fact-check and
  the gate. Building on them keeps weekly.py's rule that credit is copied,
  never typed (`source_post`, "stem#N" for an item). Reading the sheet
  would also need gspread before the brief, and `weekly.py` is stdlib so
  that it runs before `pip install`.
- **Fresh means `FRESH_DAYS` (10)**, the Drop's `MAX_STORY_AGE_DAYS`. When
  nothing fresh is left, an older run post: its repo is verified and
  running it is the subject.
- **Claude picks from a menu.** No record says whether a model's weights
  can be downloaded, so code lists the candidates and the writer reads the
  sources. A pick from outside the menu is refused by `finish`.
- **The ladder is code** (`formats.LADDER`), checked term by term, so that
  every Sunday reads the same and two weeks can be compared. Machines, not
  VRAM figures: the owner's test was that a reader should not have to do
  sums.
- **`figure_sources`.** Memory and speed figures are rarely in the paper.
  They come from quantization tables or calculators, and that is where a
  confident wrong number gets in. Each figure names its URL, or its line
  says "estimated" and its entry names the arithmetic. The fact-check
  follows them, and treats a figure with no source as a BLOCK, by §7b's
  rule for run posts.
- **The cover is the verdict.** "Requirements of model X" is a label;
  "Yes, it runs on a MacBook Air" answers the question the reader came with.

## The watch

`watch.check_weekly()` asks about each kind within its own week, from the
day after its weekday. Sunday is the last day of the week, so that rule
would never ask about it. Sunday's kind is asked about on the Monday after,
once.

## Not built yet

Hype Check, Incident Report and True or false?. Their spec is phase 4 of the
2026-10-12 plan. When a second one is built, Sunday stops being one kind:
`weekly.KINDS` would have two kinds on weekday 6, and the gate's lookup by
weekday would need to pick one by ISO week (`sunday_kind()` in the plan).
That is not built ahead of time, while there is only one kind to pick.
