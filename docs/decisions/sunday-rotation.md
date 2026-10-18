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

## One slide for the ladder, and the rewrite

The owner picked all five machines on one slide over two slides of three
and two: the ladder is something to compare, and comparing across a swipe is
harder. Five entries fit at the sheet's type size only while each is one
line, so `MAX_RUNG_WORDS` (8) caps a rung's line and `finish` refuses a
longer one. Leaving it to `proof.py` would have held the post at the gate
instead.

A refusal used to end the run, and a person had to dispatch the whole post
again. Since this change, `weekly.yml` gives the writer one rewrite, with
`finish`'s reasons in `/tmp/weekly/finish.log`, for every kind and not only
this one. A draft refused twice fails the run as before, with the Telegram
failure notice.

## The watch

`watch.check_weekly()` asks about each kind within its own week, from the
day after its weekday. Sunday is the last day of the week, so that rule
would never ask about it. Sunday's kind is asked about on the Monday after,
once.

## The Incident Report, and the rotation

Built the same day, the second format. Two kinds share weekday 6, and
`weekly.scheduled()` gives Sunday to one of them by ISO week, in `KINDS`
order. The gate, `due` and `watch.check_weekly()` all ask it. Week 42, the
day the first reference went out, is even, which is why the reference comes
first in `KINDS`.

- **Its subject is an evergreen row, not a published post.** Incidents are
  evergreen and the queue already holds them with a primary and a credit.
  Rows are marked `**Kind** — incident` by a person, because "is this an
  incident with a stated cause and fix" is a judgement. #9 (Uber, Tempe) is
  a death, and the owner did not ask for one on a rotation.
- **`src/evergreen.py`** holds the row parser. `draft.py` had it, and
  `weekly.py` cannot import `draft.py` (gspread, before `pip install`). A
  second copy of the regexes would have been a second place for the
  queue's shape to drift.
- **`incident_report`, a fifth label.** These sources are post-mortems and
  official findings. With `peer_reviewed: false` the slides would have said
  "Preprint", and with `true` the archive page would have said
  "Peer-reviewed". Both are false. The label is code's (`weekly.py`),
  like `news_report`.

### The timeline slide

The owner went through five versions on 2026-10-18. The "1/3" ghost read
as the Breakdown's. Solid black, outlined, monospaced and light timestamps
were all off-brand. What stayed is the brand's glass: each entry is
"<time>: <Sentence>", the slide shows the whole entry as text, and the time
is set again as the glass ghost. One layout option carries it, in
`slides_layout.js`, opt-in:

- `data-fill`: the layout pass tries the phrase on 1–4 lines and keeps the
  break that sets it largest in the room under the text. "About 36 seconds
  in" fills the slide as "About 36 / seconds / in". The owner chose that
  over a smaller version with no single short word on its own line.
- Every bottom ghost, in every format, now sits clear of the grid's centre
  tick (y 1130–1240). The tick used to cut through the glass, and it did
  so in Breakdowns before this format existed.
- On cream (slide 2) the glass is shaded with the post's lead hue at 28%,
  not 9% ink. The ink shade read as grey glass. A strong lead (signal's
  pink) at 45% read as solid paint, and 28% keeps both looking like glass.

`finish` refuses an entry that is not "<time>: <Sentence>", a time over
`MAX_TIME_WORDS` (4) words, or a sentence that starts in lower case. The
writer gets one rewrite.

## Not built yet

Hype Check and True or false?, phase 4 of the 2026-10-12 plan. Each would
be a third kind on weekday 6, and `scheduled()` already handles any number
of kinds.
