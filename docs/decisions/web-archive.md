# The web archive

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

## Web archive

`src/site.py` builds `posts/*.json` into a static site — an index plus one
page per carousel — deployed to GitHub Pages by `.github/workflows/site.yml`
at <https://kemval.github.io/gummietechContent/>. That URL is the Instagram
bio link.

It exists because Instagram does not make caption URLs clickable. `draft.py`
records `source_url` and `render.py` writes it into `caption.txt`, but slide 5
can only print `attribution` as flat text, so without this the source never
reaches a reader.

### Spanish

Every page carries both languages and shows one, toggled by the globe in
the masthead. `site.py`'s `t()` writes each translated string into the DOM
twice and CSS shows the half that `<html data-lang>` names, so switching
needs no second set of pages and no rebuild. The choice is remembered in
`localStorage` and applied before paint, so a reader picks Spanish once and
the whole archive stays Spanish.

The Spanish itself is the post's `es` block, written by `src/translate.py`
from the same free LLM tier as scoring — `ES_FIELDS` in `render.py` lists
the fields, which are exactly the ones a page renders. `caption` and
`hashtags` stay English because Instagram posts in English; `alt_text`,
`<title>` and the meta description stay English because one language has to
win for crawlers and link previews.

Two things that are deliberate:

- **Partial Spanish degrades to none.** A block missing a field is dropped
  whole, with a warning. A reader who gets a Spanish hook over an English
  catch cannot tell a missing translation from a careless one.
- **The toggle is only rendered when the page has Spanish**, and only
  revealed by JavaScript. A button that rearranges the furniture around
  unchanged English advertises an edition the archive does not have.
- **A translation records the English it came from.** `translate.py` stamps
  the `es` block with a hash of the fields it translated, under `_en` — not a
  field any page renders, so `site.py` and `telegram.py` never show it. A post
  whose English is corrected at the gate is then re-translated by an ordinary
  `python src/translate.py`, rather than skipped as already translated while
  its Spanish goes on saying the old thing. A block written before the stamp
  existed carries none, and counts as unknown rather than stale: it is skipped
  as it always was, so nothing already reviewed is silently rewritten.
- **Two calls, translate then proofread.** The second reads the Spanish
  against the English and fixes meaning drift, broken grammar and English
  words left in the sentence. Until 2026-09-28 the prompt also held each field
  to the English length "for a fixed layout", which was never true — Spanish
  renders only on these pages — and the squeeze produced the broken phrasing
  ("Nueve de diez revisados populares"). The model is the ceiling:
  `openai/gpt-oss-20b` still leaves errors after both passes;
  `openai/gpt-oss-120b` on the same free Groq key did not, in a dry run over
  the three worst posts.
- **Written in Spanish, not translated into it** (2026-09-30). Even on the
  120b model the Spanish came back grammatical and unmistakably translated
  ("Se pidió una ejecución… Se obtuvo una…"). Three causes, all in the
  prompt: it asked for "usted-free impersonal phrasing", which is the
  passive-*se* chain; every rule was about fidelity, so the model calqued
  telegraphic slide copy sentence by sentence; and the proofread was told
  "do not restyle correct Spanish", so stiff-but-correct was its ceiling.
  Now the voice is *tú*, the task is "as a Spanish-speaking science writer
  would put it" (the fidelity rules stay — each is a real failure), the
  proofread rewrites what a native writer would not have written, and both
  prompts carry posts a person rewrote by hand, from
  `docs/es_examples.json`. A post is never shown its own example.
  Gemini was to be compared and was overloaded both times; the model stays
  `gpt-oss-120b`, which still slips back into the passive now and then — the
  gate is where that gets caught. The examples add ~1.5k tokens a call
  against Groq's 8,000-a-minute cap, which the 429 backoff absorbs.
  A reply that is not a usable JSON object is asked once more before the run
  stops: gpt-oss returned a list despite JSON mode, and that used to end the
  run with every later post untranslated.

Machine-written Spanish on a permalink is the same credibility risk as an
unlabelled preprint, so it goes through Layer 5 like everything else: run
`python src/translate.py` and read what it prints **before** adding
`published_at`. `python src/translate.py --check` answers "is any of this
stale?" without an LLM call, and is what `check.yml` runs on every push.

Two rules:

- **It is not a blog.** Every page is a pure function of the draft JSON. Do
  not add a field that requires writing prose per post — that is a second
  content product, and the time for it does not exist.
- **`published_at` is the human gate.** `draft.py` writes into `posts/` before
  approval, so `site.py` skips any post without that date. Do not add a
  fallback that publishes undated posts. Layer 5 applies to the web too, and a
  wrong post on a permalink is worse than a wrong post in a feed.

**Every page carries link-preview tags,** and a post page uses its own slide
1 as the image: `site.py` renders `<slug>/cover.png` through `render.py`'s
`render_html()` and `open_page()`, so the preview is the cover that went out
rather than a second design of it. Instagram does not make links clickable,
so this archive is mostly reached by a link pasted into a DM, and a bare URL
there is one nobody taps. `SITE_URL` in `site.py` makes the tags absolute. So
`site.yml` now installs Chromium (about a minute per deploy). A build where
the browser will not launch warns once and ships text-only previews rather
than failing: a laptop that has never rendered must still be able to build
the archive.

`site.py` skips a malformed post with a warning instead of exiting — the
opposite of `render.py`, which is right to hard-fail the one post it was asked
to render. One bad draft must not take the whole site down.

## The moving backdrop (2026-09-30)

The archive wears the carousel's v3 look, so the bio link and the grid are
one account. `templates/backdrop.js` is the single shader, included by both
`slides_layout.js` and `site_base.html`. Stills, clips, reel and archive
cannot drift apart.

- **Surfaces.** Cream ribbons behind the whole page (a fixed layer), the
  post's lead ribbons behind its hero, and the dark ribbons behind the
  pitch. Index entries are frosted glass (`backdrop-filter`) tinted with
  their lead hue.
- **Live, and still when asked.** The page runs the loop on the reader's
  GPU and repaints only surfaces on screen. `prefers-reduced-motion`
  gets one still frame. No WebGL gets the flat colours of before.
- **Contrast.** It follows the slides' argument: every light ribbon hue
  clears 4.5:1 against ink, and glass tints mix only light hues. The
  tagline, the empty-state line and the foot were diluted ink, which fell
  to 3.6:1 over the sky ribbon, so they are full ink now, the slides' rule.
- **An edge artefact.** Scaling the small shader picture up sampled the
  row beyond it and drew a light line along the top of the page.
  `backdrop.js` samples 1.5px inside every edge.

