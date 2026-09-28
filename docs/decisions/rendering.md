# Rendering, colorways, reels and proofing

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## Rendering

Slides render at **1080×1350** (4:5). Each slide is a `.slide` div inside the
template its `post_type` names — `templates/<post_type>.html`, falling back to
`drop.html` with a warning; screenshot each individually with Playwright
rather than capturing the page.

**How many slides a format has is the template's business.** `render.py`
discovers them with `querySelectorAll('.slide')` in document order rather than
listing ids, so adding a format is adding a template. It refuses a template
rendering fewer than `MIN_SLIDES` (4): below that there is nowhere to put the
bookends, the rest slide and the catch.

Design tokens are locked — do not change them or propose alternatives.
They live in `templates/tokens.css`, which both `drop.html` and
`site_base.html` include, so the slides and the web archive cannot drift
apart. Do not copy these values into a third place:

```css
--pink:  #EE6EC0;   /* field */
--olive: #B2BC5F;   /* field */
--cream: #F7EFE2;   /* neutral field, always slide 2 */
--ink:   #3B2C23;   /* outline + type, not black */
--blush: #F9A8D4;   /* field, sparing */
--sky:   #7FB2E5;   /* field */
--amber: #F2B441;   /* field */
```

Type: Outfit 800 for display, Figtree 500/700 for body, both Google Fonts.
Signature element: a 10px `--ink` border, 44px radius, inset 34px from the
canvas edge, on every slide.

### Colorways

The hues rotate per post; the *rhythm* is what is fixed. Never hardcode a
field colour in the template — address colour by role (`--field`,
`--on-field`, `--frame`, `--flag-bg`/`--flag-fg`) and let the modifier class
set the hue, or the dark slide breaks the moment the palette rotates.

`COLORWAYS` in `src/render.py` is the single source of truth. Each family is
a `(lead, support)` pair, and a five-slide Drop renders
`lead · cream · support · dark · lead`:

| family | topics | lead | support |
|---|---|---|---|
| `signal` | AI, computing, software, robotics | pink | olive |
| `orbit` | space, astronomy, physics | sky | pink |
| `bloom` | biology, medicine, climate, ecology | olive | blush |
| `ember` | energy, materials, engineering, chemistry | amber | pink |

Invariants that keep the grid recognizable, and that a new family or a new
format must respect. `render.rhythm()` is these rules as code, which is why a
longer format needs no new palette decision:

- `--ink` is the type, the frame and the dots on every light slide.
- Slide 2 is always `--cream` — the rest slide.
- **The catch is the second-to-last slide** and always drops to `--ink`; its
  frame and preprint flag carry the post's lead hue. `proof.py` finds it by
  its field rather than by its id, because it is slide 4 of a Drop and some
  other number of a Breakdown.
- **The first and last slides share a field** — the hook and CTA bookend the
  post.
- Everything between the rest slide and the catch alternates support and
  lead. A longer format only ever extends that middle, which is the only part
  it adds.
- A new lead or support hue must clear 4.5:1 against `--ink`. `tests/` asserts
  this for all five current hues rather than trusting it.
- **No two consecutive posts share a field.** `rhythm()` refuses to put the
  same hue on two neighbouring slides; `render.vary()` is that rule one level
  up, between posts. Topic alone cannot hold it: a science feed clusters, and
  four families divided among everything published means neighbours collide
  often. On 2026-09-18, 09-19 and 09-20 the topics were materials, biohybrid
  robotics and applied thermodynamics — all `ember` — and three amber posts
  shipped in a row while every mapping worked exactly as documented.

`vary(chosen, previous)` returns `chosen` untouched unless the post before it
already had that family, in which case it takes the next family in
`COLORWAYS` order — deterministic, so a re-render of an approved post cannot
come back a different colour, and guaranteed to differ from `previous`
because it only ever runs when the two are equal. The topic keeps its own
family in the ordinary case; the rule only fires on a collision.

`previous_colorway()` answers what "before" means, and it is strictly the
predecessor rather than the newest other post: a post being re-rendered sits
in `posts/` with successors after it, and answering with one of those would
compare it against a post nobody has seen yet. `post_order()` is the order a
reader meets them — `published_at` when there is one, the filename's date
when there is not, so a drafted-but-ungated post sits where it will land. Both
skip `posts/era*.json` by the same date-prefix filter `resolve-post` needs.

`draft.py` applies this to what it writes. A Breakdown is written by hand and
never passes through it — 2026-09-20's was the third amber post for that
reason — so `render.py` warns at render time when a post repeats its
predecessor and names the `--colorway` that breaks the run. It warns rather
than rewrites: `render.py` renders the record it was given.

`draft.py` picks the family and `render.py` resolves it, so an invented name
falls back to `signal` with a warning rather than reaching the CSS. A template
asks for its own rhythm with `{% set fields = rhythm(5) %}`: the template is
what knows how many slides it has, `render.py` is what knows what colour they
go in, and neither has to be edited when the other changes.
`render.py --colorway <name>` overrides the JSON at the human gate.

### Drop reels

A published Drop can be rendered as a silent ~19s 1080×1920 reel by
`src/reel.py` — the **Drop reel** row in `docs` §1, on request only. It is
not The Build, which stays a person's, start to finish. Five things that are
deliberate:

- **It has no words of its own.** `reel.html` includes
  `drop_slides.html`, the same partial `drop.html` does, through the same
  `render_html()` context. That is why it skips the fact-check, and why
  `reel.py` refuses a post without `published_at`: every claim in it has
  already passed the gate. `--draft` is for a local preview and the smoke
  fixture only.
- **Captured frame by frame, not recorded.** Playwright's video recorder runs
  in real time and drops frames on a slow runner; its fake clock drives JS
  timers, not CSS animations. So every animation is paused and stepped
  through the Web Animations API, and the PNGs are piped into ffmpeg. Same
  JSON, same video. The template owns the length — `reel.py` reads it off
  the animations' end times — as it owns the slide count.
- **ffmpeg is not on `ubuntu-24.04`.** `reel.yml` and `check.yml` apt-install
  it. It is the one non-Python tool in the pipeline.
- **Instagram draws over a reel** — the top ~200px and the bottom ~400px —
  so the slides sit in a card scaled to 0.9 between y=300 and y=1515.
  `reel.py` measures each settled scene against `SAFE_TOP`/`SAFE_BOTTOM` and
  reports a `PROOF ·` verdict that gates the button like any other.
- **The preprint flag is on every frame, and that is checked per frame.**
  On the carousel it rides the catch slide; in a video a label on screen for
  three seconds is not a label. `reel.py` aborts, deleting the video, on the
  first frame where `.reel-flag` is not fully visible inside the safe zone.

Audio is never added: trending audio can only be chosen in the Instagram
app, and choosing it is a person's call.

### Proofing the render

`render.py` warns on word count but never looks at the PNGs it produces, and
`hook_size_class()` sizes the hook from its character count, not a measured
layout — so a long compound word, a body field a few words over budget, or a
palette rotation that puts pale ink type on a washed-out field can overflow
the frame, fail contrast, or clip the preprint flag without any error.

`src/proof.py` is the check that runs on every post, including in CI. It
measures rather than looks: every one of those failures is a number in the DOM
of the page `render.py` is about to screenshot, so it reads bounding boxes,
`scrollHeight` and computed colours off the live page and reports
BLOCK / FIX / PASS. It shares `render.py`'s `open_page()` — a layout checked
in a differently-built page is a layout nobody checked.

```bash
python src/proof.py posts/2026-09-15-tides.json      # exits 1 on BLOCK
```

Three measurement choices that are load-bearing:

- **What gets measured is decided by shape, not by a list of class names.**
  It used to be a CSS selector naming every class, and a template with new
  ones was simply not measured: `templates/signal.html` shipped its credit
  line overlapping the wordmark by 18px on five slides, and a rank numeral
  at 1.5:1, and this file reported PASS. Now every element inside the frame
  that carries text and has no texted children is measured, so a new format
  is covered without anyone remembering to register it. `CHROME` is still a
  list, and that is fine: a class missing from *it* is merely held to the
  stricter bar and says so loudly. Silence is the failure worth engineering
  against.

- **Collisions are tested against line boxes, not element boxes.** The
  element box of a left-aligned block spans the full column even when its
  last line stops short, which made `.source` and `.dots` on slide 5 overlap
  by a constant 3px in a layout where no glyph is near another — it BLOCKed
  all 13 existing posts. Range rects are both quieter there and stricter
  where it matters: a line that really does reach the dots is still caught.
- **The contrast bar is 4.5:1, from this file's own colorway invariant,**
  not WCAG's 3:1 for large text. Chrome (`.domain`, `.wordmark`) is held to
  3.0 instead and only ever reported as FIX, because its `opacity: 0.75` is a
  locked design decision and pink already sits at 3.26:1 — BLOCKing on it
  would fail every post every day. Content type is at full opacity and clears
  4.86:1 at worst, so the strict bar there is real headroom, not luck.

**It also carries the one rule that is not about this post's pixels.**
`check_colorway()` reports a post that repeats its predecessor's field, as a
FIX. `render.py` already says this, to a run log nobody reads at the gate;
this report is carried into the Telegram message, which is the last place the
rule can still be acted on — after approval the post is on the grid. A
record-level check in a file that otherwise measures the DOM, for the reason
`check_words()` is one. FIX and not BLOCK because a repeated hue is cosmetic,
and withholding the button over one teaches a person to tap "Posted anyway"
without reading. It skips a path outside `post_order()`: the `era*.json`
fixtures are not posts, and `previous_colorway()` treats a path it cannot
find as arriving at the end of the archive, which made every fixture report
as clashing with the newest real draft.

The `slide-proof` agent (`.claude/agents/slide-proof.md`) still exists for
what a measurement cannot answer — whether the slides *look* wrong. Run it
locally on a post that matters. It is read-only: it never edits the JSON or
renders into `output/`, and like `proof.py` it does not check claims or
wording accuracy — that is `fact-check`'s half.
