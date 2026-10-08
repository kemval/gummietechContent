# Deduplication: a story is a paper, not a URL

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**The queue is deduplicated by URL, and a story is not a URL.** Many feeds
cover one press release; each copy is its own row with its own score, and
the siblings of the row that gets drafted stay queued forever. On
2026-09-17 the top row of the queue was the paper published that same
morning. So `draft.py` resolves each candidate's paper *before* the LLM call
and skips a row whose DOI or Crossref citation already appears in `posts/`,
marking it `duplicate` in the sheet. It gives up after `MAX_DUPLICATE_SKIPS`
fetches rather than walking the queue inside a 15-minute job. A candidate
named by hand — `--row`, `--url`, an evergreen brief — warns and drafts
anyway, because naming one is the override. Coverage with no resolvable DOI
cannot be matched at all: that is the `fact-check` agent's step 8, which reads
`posts/` and can see what a key cannot. `feeds/tier5_depth.yaml` is a whole
tier of that case — essays have no DOI, so nothing about them is deduplicated
and `attribution` and `peer_reviewed` both come from the model rather than
from Crossref. The feed file's header says what that costs; it is the reason
that tier is two feeds and not twenty.

**The duplicates are cross-headline, which is why the DOI is the only key
that finds them.** This file used to say forty-five feeds carry one press
release into a queue of 1440 rows. Measured on 2026-09-21, both numbers were
wrong and the shape they implied was wrong with them:

| | said | measured |
|---|---|---|
| rows in the sheet | 1440 | 4864 — 1383 `queued`, 3044 `rejected`, 24 `drafted` |
| copies of one story | ~45 | largest title-group 3; 56 of 57 groups are pairs |

Outlets rewrite the headline. Phys.org, EurekAlert, ScienceDaily and the
university newsrooms each write their own, so the copies do not look alike
as strings even when they report the same paper. Grouping the whole sheet by
normalised title finds 57 stories with more than one row and would retire 58
rows, 22 of them `queued` — 1.6% of the queue. Probed the other way round,
sixteen of the 24 rows already drafted have no other row in all 4864 that
shares even three content words. A pair that really is one story scores
0.27:

```
"Ancient proteins identify various Denisovan remains from Southwest China"
"First Denisovan forearm bone discovered in southwest China"
```

So **do not rebuild title-based deduplication in front of `score.py`.** It
was written, tested and measured on 2026-09-21 and then removed: it buys
about 1% of the LLM quota, it cannot see the duplicates that actually reach
the gate, and loosening it to catch them starts merging stories that are
merely adjacent long before it catches them — at a Jaccard bar of 0.35, still
too high to pair the two lines above, the largest group is already 17.
Lowering `MAX_DUPLICATE_SKIPS` on the strength
of a title pass would be the same mistake wearing a different hat. The paper
is the identity; `resolve_paper` is what recovers it, and paying a fetch per
candidate is what that costs.

One consequence for strategy: `docs` §Layer 2's fifth automatic reject —
"anything already covered by three or more large accounts" — is absent from
`score.PROMPT` because a model reading one headline cannot know it, and the
sheet cannot cheaply tell it either. It stays unimplemented, and that is a
measurement rather than an oversight.

**A launch has no DOI, so its key is its maker's page (2026-10-07).** Once
launches could reach the queue, the DOI could not find their duplicates:
GPT-6 Astra arrived in 39 rows. Most were different stories (customer
cases, papers that used the model, a later model), but the launch itself
came as OpenAI's own page twice, InfoQ's report and a newsletter. Each
newsroom feed now declares where its company announces (`announces` in
`feeds/tier1_primary.yaml`, measured). A post's `source_url` is also kept
as a normalised key (`ingest.url_key`: no scheme, `www.`, fragment, `utm_`
parameters or trailing slash). A coverage row with no paper whose page
links a maker announcement already in `posts/` is a duplicate. Run against
the 39 Astra rows with Astra posted, it caught all four copies of the
launch and none of the other stories. It is a link check, not a title
match: a story that never links the maker's page (NVIDIA's own blog post
on Astra) still gets through, and the fact-check agent remains the check
for that. The links are read only to skip a row, never to choose a source
or a credit: coverage links the wrong announcement as readily as the right
one (Mistral's docs page for Large 4 linked four older Mistral launches,
and not Large 4).

