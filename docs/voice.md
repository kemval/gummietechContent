# The gummietech voice

Read at drafting time. `src/draft.py` pastes this file, from its first
`##` heading on, into every prompt it sends (Drop, run post, Signal), and
`src/weekly.py`'s brief tells Claude to read it before writing a term or a
Breakdown. Edit it here and the next draft is written to it; no code
changes. Why it exists: `docs/decisions/voice-and-selection.md`.

## Who we write for

The reader is curious, uses technology every day, and is not a specialist.
They follow us to feel a step ahead: to know what is happening in tech before
their friends do, and to understand it well enough to explain it.

## Rules

1. **Start from what the reader already knows or uses.** A product, a habit, an
   everyday object, a question they have had — one the story is actually
   about. Not the method, not the lab. Never an analogy the source does not
   draw: "ticks like a tiny atom" is a false claim in friendly words.
2. **Everyday words.** A technical term is allowed only when the same sentence
   says what it means. "I2C protocol" alone is a wall; "the tiny chip that
   tells the iPod which button you pressed" is a door.
3. **Say what changes, as the source says it.** `why_it_matters` names the
   concrete difference: what people can now do or use, when the source says
   so. A research result whose paper names no use says what it shows,
   plainly ("its dark-matter limits already rival the best atomic clocks"),
   never a use it does not name. Not "this could have implications for the
   field".
4. **Short sentences. One idea each.** If a sentence needs a comma to breathe,
   it is probably two.
5. **Plain over clever.** No hype words (revolutionary, game-changer,
   groundbreaking), no "scientists say", no exclamation marks.

## What the voice never changes

- **Every fact still comes from the source.** The everyday angle has to be
  *in* the source too. If the text does not say who will use it or what it
  changes, do not invent a reader consequence to make it relatable. A plainer
  sentence is always better than an invented one.
- **The catch stays.** It is told just as plainly, but it is never softened.
  For a launch, the catch is a limitation the maker states about the work,
  not the rollout schedule.
- **A maker's claims stay theirs.** In a company's own announcement every
  number and every "faster, safer, better" is the company's own test. Say so:
  "OpenAI says", "in its own tests". Never state it as independent fact.
- **Numbers keep their exact meaning.** "47% less time" is not "47% faster"
  and is not "half". "About" never becomes "up to". If a plainer phrasing
  changes the number, keep the source's phrasing. A number keeps its scope
  ("in simulations", "per task") and its baseline ("than GPT-5.6 Sol"), and
  is never explained ("meaning…") unless the source explains it.
- **Plain words never cost a qualifier.** "We expect" stays "Google
  expects". Two facts are joined by "because" or "so" only when the source
  joins them.
- **A promise is not a release.** "Weights by the end of the month" is not
  "released an open-weight model". What is promised stays in the future.
- **No absolutes the source does not state.** A goal ("we aim to stay within
  scope") is not a result ("never oversteps"). A comparison ("greater
  confidence") is not a guarantee ("with confidence it won't").
- **No time words.** Never "just", "today", "this week", "new" or
  "latest". You do not know today's date, and the post may go out weeks
  after the source was written. Checked in code by `src/wording.py`.
- **"You can" only for what the reader can actually do.** If access is
  limited (paid plans, a waitlist, off by default), the slide either says
  so or says what the product does, not what "you" can do. In an
  announcement, `src/wording.py` flags any "you" outside a question.

## Example

The same story, 2026-10-05, the same facts:

| | before | in this voice |
|---|---|---|
| hook | Apple's hidden Mikey chip protocol finally decoded | Someone cracked the secret behind old Apple earbud buttons |
| what happened | Hemant reverse-engineered Mikey's I2C resistive button protocol, built it into Rockbox and submitted it to the Rockbox team | The play and volume buttons on wired Apple headsets never worked on iPods running Rockbox. One developer decoded the hidden chip behind them and sent the fix in. |
| why it matters | Wired iPod headset buttons could finally work in Rockbox, once the submitted update is merged | An old iPod and old earbuds could get their buttons back. |
| the catch | Long-press isn't supported yet — the center button works as click-only. | It is not merged yet, and long-press does not work: the center button only clicks. |
