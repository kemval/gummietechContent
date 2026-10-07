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

Until 2026-09-28 the type was Outfit 800 for display and Figtree 500/700
for body, and the signature element was a 10px `--ink` border, 44px radius,
inset 34px from the canvas edge, on every slide. Both were replaced for
every carousel format and the web archive that day — see **Design v2**
below.

### Design v2 (2026-09-28)

The Drop and its reel moved to a new layout on 2026-09-28, from a mood board
the owner assembled (editorial Instagram grids and sci-tech posters: huge
fitted grotesk type, tiny mono labels, spec-sheet brackets, Figma selection
boxes). **The palette and the rhythm did not change** — the owner asked to
keep them, and `rhythm()` still colours every slide. What changed, and why:

- **Type.** Archivo (variable `wdth` 62–125) replaces Outfit/Figtree for
  display and body; IBM Plex Mono sets the labels. Geist Mono was tried
  first and dropped because impeccable's detector flags it as overused, and
  JetBrains Mono is the status-report pillar's, which must stay a separate
  system. Both are OFL and self-hosted in `fonts/` with their licences.
- **The drawn frame is retired.** The fitted giant type is the new
  signature and a 10px border boxed it in. `.frame` is kept, invisible,
  inset 34px, because `proof.py` defines "inside the frame" against it.
- **Content is never diluted.** Ink on pink is 4.86:1, so any `color-mix`
  toward the field puts a content line under 4.5. `--mute` is corner chrome
  only (`.lbl`, held to 3.0 like `.domain` was).
- **The design never writes a word.** A hand-built prototype of this design
  silently dropped "than defaults" from what_happened and turned "default
  plans" into "own planner". The template now binds every text node to a
  record field, and `render.py` only chooses spans: `emphasis()` (the span a
  selection box outlines — a figure phrase, else a keyword widened to whole
  words), `cover_figure()` and `catch_diff()`.
- **A figure is never bare.** The prototype set "81%" at 300px on the
  cover, the best-of-15 result, while the catch existed to say the model's
  own picks gave 1.40×. `cover_figure()` shows a figure only when the hook
  has exactly one, and always with the hook's own qualifier (after its em
  dash, or the rest of the clause). `catch_diff()` strikes it and sets the
  correction beside it only when the catch names that figure first and a
  second one after it; anything less regular is plain text.
- **Layout is measured, in `slides_layout.js`.** Fitting type to a column,
  docking the spec row, growing a figure-less hook into the space and
  placing the keyword cloud all need rendered glyph widths. The script sets
  `window.__ready`; `open_page()` waits for it and raises on
  `window.__layoutError` instead of screenshotting a half-laid page. It
  divides by the reel card's 0.9 scale, and `.slide` is `isolation:
  isolate`: without it the cover's z-indexed hook painted over slide 2 in
  the reel, where slides stack.
- **Breakdown and Signal followed the same day**, so the grid has one look.
  `slides.css` is again the one stylesheet every format includes, and the
  pieces they share — corner labels, cover, catch slide, follow slide, the
  selection box — are macros in `slide_parts.html`, so a format's template
  holds only its own middle. Each kind of slide gets its own composition
  (ghost "(?)" under the question, the keyword cloud over the intuition, a
  step bar and a ghost "1/3" on each mechanism step, a fitted rank and a
  `[source]` credit on each Signal item) so a nine-slide post does not
  repeat one layout nine times. A figure's box leaves a linking word out:
  "20% of" read as a typo on a Breakdown step.
- **The web archive followed too**, so the bio link matches the grid: the
  ink-bordered rounded panels became flat lead-hue blocks, labels went to
  full-ink IBM Plex Mono, sections are numbered "(01)" as on the slides, the
  pitch is set as the dark catch slide, and `site.py`'s `t()` applies the
  same `typeset`. The home page's wordmark is sized from the column
  (`calc((100vw - 36px) / 7.9)`) — at `13vw` its letters ran 31px past the
  column on a phone and the page scrolled sideways.
- **Decoration is `aria-hidden`** — the keyword cloud and the ghost words
  "(why)", "(but)", "(gummie tech)" — and `proof.py` skips it, for the same
  reason a screen reader does. `proof.py` also measures text-node rects only,
  since the selection box's handles sit outside the words by design.

### Design v3 — the grid (2026-09-30)

The owner, as creative director, said v2 still was not working and gave a
second mood board (`~/Downloads/gummietechdropDesign`: Swiss grid posters
with hairline rules and "(01)" index marks, a ruled-cell agency post, a
callout diagram with leader lines, blurred-gradient posters). v2 read as
big type on a flat field with no visible system. v3 keeps the palette,
the rhythm, the type and every text rule, and adds the system:

- **Hairline grid** (`.slide::before`, frame slides only): the frame
  edges (x 34/1046), the header and footer bands (y 110/1240), and the
  centre line (540) inside those bands only, in `--rule` (16% of
  `--on-field`). The first version ran the edge and centre lines through
  the text column and the owner read it as text overlapping. The cover
  drops the footer rule because its spec row sits there.
- **Bottom ghost words clear the footer band.** They are lifted by
  `106px + .22em` (parentheses and descenders hang below the line box),
  and they are placed *after* body text grows. The shrink scales from
  the ghost's own width, not the column's: a capped short word ("1/2")
  never fills the column, so the old formula never shrank it. That bug
  predates v3 and was hidden by the old 60px anchor.
- **Top-anchored ghost words shrink to clear the section rule below**
  (40px plus the .22em overhang). The catch text grows upward, and its
  rule cut through the bottom of "(but)". The owner chose this over
  capping the text (which kept "(but)" full width but left a dead gap):
  the catch is the post's most important line.
- **The selection box is padded in em** (`.16em`), because body text now
  grows to 92px and a fixed 10px gap let the outline touch the boxed
  word's last letter.
- **The backdrop is Neat's moving colour ribbons, drawn by our own shader
  and filmed as a looping MP4 per slide.** The owner asked for Neat
  (github.com/FireCMSco/neat) in motion. Neat's licence allows this use,
  but its code draws a "NEAT" watermark into every render unless a key is
  bought (€12 per domain; `if (!this._licensed) renderWatermark`), which
  the $0 budget rules out, and hiding the mark would be dodging their
  paywall. So its technique is reimplemented in `slides_layout.js`, not
  its code: palette colours layered wherever a horizontally-stretched 3D
  simplex noise (Ashima, MIT) crosses a threshold, curled by `cos()` flow
  warps, over a lit waving surface. Two earlier attempts, a single hue
  shaded and soft folds, were rejected as "not Neat": it is the layered
  colours that make it.
  - **Contrast holds on every frame by construction.** Light slides use
    only palette hues, and every one clears 4.5:1 against ink (`RIBBONS`,
    field last and widest so the slide still reads as its colour); their
    lighting only brightens. The dark slide's ribbons are ink, ink ×.45 and
    one lead-tinted ribbon capped so 22px lead-hue labels keep 4.5:1; its
    lighting only deepens. proof.py measures the flat field, so this
    argument is what covers the canvas.
  - **The ribbons are the post's own palette** (owner's call, 2026-10-06):
    a light slide's ribbons are its post's lead, support and cream, minus
    the slide's field, field last. `<body data-palette>` carries the pair
    from `render_html()`; an archive post page carries it on `.page-bg`.
    The fixed `RIBBONS` table put pink and sky on every field, so all four
    colorways read pink-and-blue and `vary()` was invisible under the
    ribbons — compared side by side on one post per colorway before the
    change. Contrast is unchanged: the palette hues are the same ones. The
    table survives only for the archive index, which has no post. Pink
    remains in every family (pink or blush in all four `COLORWAYS`); that is
    the palette, not the ribbons.
  - **Seamless and deterministic.** Time enters only as the angle of one
    8s loop (noise sampled around a circle), seeded by the hook and slide
    id. Frame 0 and frame 8000ms are byte-identical. The PNG is frame 0.
    `render.py` films each slide over one loop (JPEG frames, TV-range
    yuv420p, which Instagram expects), and `--no-motion` skips it.
    `reel.py` stretches the backdrop's clock to a whole number of loops
    per reel, so the background does not jump where the reel loops.
  - **Ghost words are frosted glass.** The owner rejected the outline and
    three other type treatments. `glass()` paints "(why)", "(but)" and
    "1/2" into the backdrop canvas: the backdrop blurred and brightened
    inside the glyphs, a soft shadow, and a bevel (the glyph minus itself
    offset, because a stroke traced the variable font's overlapping
    contours as a box inside the "t"). Font and position are read off the
    DOM element, which stays in the page, transparent, for the layout
    pass and proof. Without WebGL the outline returns.
  - **The reel has no card.** The owner asked for the moving backdrop
    alone, full screen. The content floats on the 9:16 backdrop, still
    scaled to 0.9 in the safe zone, with no background, grid or grain of
    its own. The glass words are painted on the backdrop for their scene.
    Scenes fade out, then in: a swipe or a cross-fade layered two scenes'
    words. The first slide's zero-length fade-in keeps reel.py's scene
    start at 0. Repainting skips anything covered in a stack, and a reel
    takes ~5 minutes. The keyword callouts assemble in order (tag, wire
    out, wire down, dot), indexed by `--i` from the layout pass, because
    the owner noticed slide 2's diagram was the one thing that just
    appeared.
  - **Finishing pass (owner's list, 2026-09-30).**
    - The footer band's rules are measured from the bottom, so a 9:16
      Build still no longer has a 4:5 rule across its middle.
    - On cream, glass shades rather than brightens: "(bug)" had vanished.
    - The follow slide's "(gummie tech)" is glass, drawn line by line.
    - A figure-less cover keeps its open band, showing only the moving
      ribbons. A glass "(drop)"/"(signal)" was tried there; it repeated the
      format label on most covers, and the owner chose nothing.
    - Signal ranks are capped at 200px, and the claim is centred under
      the rank.
    - Hubot's zero is slashed with no plain alternate, and read as "θ".
      U+0030 alone comes from Mona Sans via unicode-range, on the slides
      and the archive.
    - Status reports are untouched: their own design system, by hand.
  - **Cost.** Headless Chrome runs WebGL on the CPU, so the shader draws
    at a third of the size and is scaled up (Neat's `renderScale`). The
    ribbons are smooth enough not to show it. At full size a reel took
    over fifteen minutes; now a Drop's five clips take ~3 minutes, added
    to `review.yml`, which now installs ffmpeg. In the reel only on-screen
    cards are repainted. The motion was slowed at the owner's request by
    shrinking the noise's circle per loop, not by lengthening the loop, so
    clips stay 8s. `check.yml` renders with
    `--no-motion`; its reel smoke drives the backdrop's clock. Telegram
    sends the clips after the stills, all or none.
- **The hook sits on ruled baselines** (.84em at line-height 1.0).
- **Ruled cells**: the spec row and every section label get a full-ink
  top rule; spec cells are split by hairlines.
- **Ghost words are outlines**, not 13% fills: the fills read as muddy
  tone-on-tone. On the dark slide the outline is the lead hue.
- **The keyword cloud is retired** for callout tags. It repeated three
  phrases forty times. Each keyword (at most four, deduplicated) now
  sits in a ruled tag with a "(01)" index, wired to a dot on the section
  rule below. Left and right wires step outward so none cross.
  Still `aria-hidden`: the keywords are decoration, and the caption
  carries them.
- **Body text grows only a little**, from 60px up to 72px, and a cover
  hook without a figure grows from 96px up to 120px (v2 allowed 176px). At
  92px and 160px everything shouted at one volume, and the owner preferred
  2026-09-28's scale: a medium hook, calm body text, one huge element.

- **GitHub's type system replaces Archivo and IBM Plex Mono.** Hubot Sans
  (display, at 105–125% width), Mona Sans (body) and Monaspace Neon (labels),
  all OFL and self-hosted in `fonts/` with their licences. The owner
  rejected a first round of "tech" faces (Doto, Michroma, Kode Mono,
  Tektur, Unbounded) as gimmicky. Then four OFL systems were set in this
  one layout: GitHub's, Vercel's Geist, IBM Plex, and Funnel Display with
  Fragment Mono. The owner chose GitHub's. Fontshare faces (Satoshi,
  General Sans, Switzer) were ruled out because their licence forbids
  self-hosting the files. Hubot's zero is slashed and has no plain
  alternate; that was kept, since it was in the sketch the owner picked.
  Hubot's taller line box pushed the Signal's rank into the corner label,
  so its `data-top` is now 140.

proof.py passes all four fixture formats unchanged, and so does the reel.

### Reel motion and The Build's kit (2026-09-28)

- **The reel performs the design's two signatures.** The selection box
  draws left to right and its handles pop; on the catch, the "−" row rises,
  a line strikes its figure, then the "+" row rises. The honesty moment is
  the one that moves most. Both are real elements (`.box`, `.strike`) in
  `slide_parts.html`: the carousel renders them statically, identically,
  and the reel animates them — a `::before` or `text-decoration` cannot be
  animated where reel.py seeks frame by frame.
- **It loops.** After scene five the cover swipes back in and the reel
  ends as it lands, plus one frame (at 30fps the last captured frame fell
  17ms short of landing and the seam showed). The returning cover is slide
  1 cloned in the page before the layout pass, so it cannot differ from the
  cover; it is a `.card > .loop`, not a `.card > .slide`, so reel.py still
  counts five scenes. First and last frames measure 43 dB apart — encoder
  noise between an I-frame and a P-frame, not a visible jump.
- **The Build gets stills, not a generator.** It is a person's reel start to
  finish (docs §1). `src/build_kit.py` renders four 1080x1920 PNGs from one
  episode of `docs/build_episodes.md` — cover (the Drop's hook styling, as
  the Build rules require), problem card, a transparent lower third, end
  card — for the editor. Every readable word sits inside both the reel's
  safe zone and the profile grid's 4:5 crop of a reel cover (y 285–1635);
  the first version put the corner labels at y 281.

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
| `ember` | energy, materials, engineering, chemistry | blush | amber |

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

**Ember is blush/amber since 2026-09-30.** Under the v3 backdrop amber read
as washed out as a lead. Ember first took signal's pink/olive, 09-28's look,
but that left the grid three looks for four families. Blush is the one lead
no other family uses, and the owner chose amber for its support slide over
sky and olive. `vary()` compares colour pairs, not names, from those hours
when two families shared one; the test for that case stays.

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
