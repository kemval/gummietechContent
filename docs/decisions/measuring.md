# Measuring

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## Measuring

Layer 7. `docs` §9 makes saves the primary measure and shares the second,
`profile_visits` is the funnel one, and likes are explicitly not a metric.
§8 sets the decision it exists for: after thirty posts, cut the weakest
format and double the winner.

Instagram's numbers sit behind the Professional-account API that §4 rules out
on cost, so they are read by eye. The only design question is where a person
types three numbers with the least ceremony, and the answer is the chat the
gate already lives in.

`confirm` therefore does two jobs on the same poll: it stamps
the taps, and three days after a post went live it asks that post's numbers
and writes the reply into the post JSON. Four things hold it together:

- **The ask writes the block, not the answer.** `metrics: {asked_at}` is
  written when the question goes out, because that block is also what stops
  the question being asked again on the next poll. An unanswered ask is
  a block with no numbers in it, which `learn.py` reports as unanswered
  rather than as a zero — those are very different facts.
- **The answer is a reply, not a button.** Three integers do not fit in
  `callback_data` and no keyboard can carry an arbitrary number, so `confirm`
  asks Telegram for `message` updates as well as taps and reads the stem back
  out of `reply_to_message`. Nothing new is stored to link the two — which
  makes the reply *gesture* load-bearing. Three numbers typed as an ordinary
  message name no post, and `record_metrics` drops them: with several asks
  outstanding at once, which is the normal state, nothing can say which one
  they answer, and guessing would put invented numbers into the §8 decision.
  Asking in words did not secure it. The message has said "Reply to **this**
  message" in bold since it was written, and on 2026-09-21 nine answers
  arrived unreplied over a single day and every one was lost. So the ask
  carries `METRICS_FORCE_REPLY` — Telegram's `ForceReply`, which has the
  client open the reply box already pointed at the question, so the link is
  made by the keyboard rather than by remembering. The sentence stays, for
  whoever dismisses the keyboard.
- **It survives the missing offset like `published_at` does.** Recording a
  number is a set, not an increment, so a reply replayed for 24 hours writes
  what is already there. Two replies that disagree are a correction, and
  `getUpdates` returns them oldest first, so the later one lands last.
- **A numbers-only poll does not rebuild the archive.** `site.py` ignores
  `metrics`, so a rebuild would produce identical HTML. `confirm` reports
  `published=true|false` on `GITHUB_OUTPUT` and `publish.yml` dispatches
  `site.yml` on that. Do not go back to reading it off the diff: writing a
  metrics block next to `published_at` puts a comma on that line, so the diff
  claims a publish on a poll that published nothing.

`python src/learn.py` is the report — medians by `post_type`, `colorway`,
`domain` and weekday, then every measured post ranked by saves. It holds back
a group under three posts rather than ranking noise, and says outright that
§8 puts the format decision at thirty. It computes no rate: saves per
impression would be the honest measure and Instagram does not give
impressions away, so a ratio built from these three numbers would look
rigorous and mean nothing.

## Reach and follows (2026-10-09)

At thirty posts the §8 decision came due and the numbers could not carry
it: saves were 0 on all 27 measured posts, shares exactly 1 on 23 and 0 on
the rest — most likely one person, the owner, sharing each post — and
profile visits tracked how late a post was read rather than the post.
No number of further posts ranks measures at their floor. (The
`metrics-analyst` agent's report of that date; 15 of the 27 had also been
read in one sitting on 2026-09-21, days late.)

So the ask now takes five numbers: saves, shares, profile visits, then
**accounts reached** and **follows**, both on the same Insights screen and
both free to read by eye. They are counts beside the others and never a
denominator — the no-rate rule stands, and "saves per reach" would be the
same invented ratio. `METRICS_CORE` is the first three: an answer of three
(every ask sent before this, or a person without reach to hand) or four
still records and still counts as answered in `learn.py` and `watch.py`,
and a field not given is missing, not zero — `learn.py` prints it as a dash
and takes each median over the posts that have it.

Insights prints reach as "1,340", and a comma is one of the separators a
reply may use, so read raw that is two numbers and every field after it
lands one place late, silently. `metrics_reply()` drops a comma with exactly
three digits after it and no space before matching; the price is that
"150,200,400" typed without spaces no longer reads, and is ignored rather
than misfiled.
