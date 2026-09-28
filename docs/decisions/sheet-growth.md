# The sheet grows forever

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**The sheet grows forever, and that is fine — do not build a purge.** Nothing
deletes a row, so `rejected` accumulates: 3044 of 4864 rows on 2026-09-21.
Measured the same day, the growth costs nothing worth code. `get_all_values()`
over the whole sheet takes 0.77s; 48,650 cells of the 10,000,000 a spreadsheet
allows; ~247 rows a day, which reaches that ceiling somewhere around 2037.

The reason not to purge is sharper than the reason not to bother.
**`rejected` rows are the deduplication memory.** `ingest.existing_urls()`
reads the whole `url` column and drops anything already there, so deleting a
rejected row does not free a row — it re-ingests the item on the next cycle
and pays `score.py` to reject it again. That trades storage, which is free
and effectively unbounded, for the free tier's daily request cap, which is
the one budget in this pipeline that actually binds.

Two facts about the sheet worth knowing before measuring anything on it.
Rows 1331-1737 are 407 completely empty rows, left by a write that went
wrong; they are inert, since `score.py` looks for `new` and `draft.py` for
`queued`. And because of them a naive count of repeated `url` values reports
406 duplicates where there are none at all — the empty string, counted 407
times. Deduplication has never let one through.

If a purge is ever genuinely needed, the only safe rule is age: a row whose
`published` is older than `MAX_AGE_DAYS` cannot come back, because
`ingest.py` would drop it on age even if the feed still lists it. Undated
rows are never safe — `ingest.py` keeps them on purpose, so they have no age
to test and would return immediately.
