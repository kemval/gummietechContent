# Evergreen queue

Candidate subjects for evergreen posts, mined from the Tier 6 sources in
`gummietech_content_system.md` §3 by the `evergreen-scout` agent.

**Compiled:** 2026-09-11 · 17 candidates, all scoring ≥ 7.0
**Checked against** every record in `posts/` as of that date — no duplicates.

This is an idea queue, not drafted content. Nothing here has been through
`draft.py`, `fact-check`, or `slide-proof`. Take a row, feed the source to
`draft.py`, then run the normal pipeline.

## Before drafting any of these

- **A Stack Exchange or Wikipedia URL is not an attribution.** Six candidates
  lead with one because it is the best *explanation* of the subject. Each row
  names the primary to put in `attribution` — carry it across, or `fact-check`
  will BLOCK on authorship.
- **Check the "settled?" column.** Two rows are not settled science and must
  say so on slide 4: #9 is a preprint (`peer_reviewed: false`, arXiv URL in
  `source_url` so `PREPRINT_HOSTS` fires) and #16 is a retracted paper.
- **#16 has no home in the drafting contract.** There is a `peer_reviewed`
  field but nothing for retraction status. Flag it by hand at the gate.
- **Family spread is ember-heavy** — orbit 4, bloom 5, ember 6, signal 3. Take
  at most three ember rows in a row if you want the grid to stay balanced.

---

## Ranked

### 1 · 8.50 · `orbit` — The tidal bulges that don't exist

**Hook** — The two tidal bulges you were taught in school do not exist.
**Source** — [Physics SE, accepted answer](https://physics.stackexchange.com/questions/121830/does-earth-really-have-two-high-tide-bulges-on-opposite-sides) · **attribute to** Laplace's dynamic theory of tides, not the SE user.
**Settled?** Textbook-settled among oceanographers, and actively mistaught everywhere else.
**Why it matters** — Tides are a shallow-water wave problem, not a static-shape problem. The bulge would need to travel ~1,700 km/h; shallow-water waves in a 4 km ocean cap near 700 km/h. The ocean can never keep up with the Moon.
**The catch** — Newton's *forcing function* is right; only his response model is wrong. Do not let the hook slide into "Newton was wrong about gravity."

### 2 · 8.25 · `bloom` — Corals stir their own water

**Hook** — Corals beat microscopic hairs to stir their own water, and heat stops the stirring before it kills the animal.
**Source** — [Quanta](https://www.quantamagazine.org/corals-spin-tiny-vortices-to-get-oxygen-but-not-if-its-too-hot-20260805/) → primary is the *Science* paper (May 2026), Pacherres/Kühl. **Pull the DOI and confirm first author** — Quanta quotes Kühl, likely senior.
**Settled?** Peer-reviewed. Mechanism established; the bleaching link is the open part.
**Why it matters** — Cilia in hexagonal arrays generate corkscrew vortices that punch through the diffusive boundary layer. Coral respiration is *active ventilation*, not passive diffusion — so warming attacks it twice: higher oxygen demand, lower dissolved oxygen.
**The catch** — Cilia fail near 37 °C, stop by 39 °C. Why they speed up under heat is unexplained, each species has its own range, and the tie to bleaching is not yet demonstrated.

### 3 · 8.25 · `bloom` — Cut grass is a distress call

**Hook** — The smell of cut grass is a chemical distress call that summons wasps.
**Source** — Brodmann et al., *Current Biology* 2008 (orchids mimicking GLVs) is the cleanest single source. Background: [Green leaf volatiles](https://en.wikipedia.org/wiki/Green_leaf_volatiles); also Whitman & Eller, *Chemoecology* 1990 (doi 10.1007/BF01325231).
**Settled?** Textbook-settled. Thirty-five years of replicated chemical ecology.
**Why it matters** — GLVs are made in seconds from membrane lipids via the lipoxygenase pathway. The plant has no nervous system but has a broadcast channel, and parasitoid wasps evolved to listen. Neighbouring undamaged plants prime their own defences on hearing it.
**The catch** — "Cry of agony" is anthropomorphism. GLVs also release from mechanical damage with no herbivore present, and priming is a faster response, not an immune response.

### 4 · 8.25 · `ember` — The tube with no moving parts

**Hook** — A steel tube with no moving parts splits compressed air into a 200 °C stream and a −50 °C stream.
**Source** — [Vortex tube](https://en.wikipedia.org/wiki/Vortex_tube) · **attribute to** Eiamsa-ard & Promvonge, *Renewable and Sustainable Energy Reviews* 12(7):1822–1842, 2008.
**Settled?** The *device* is settled and commercially sold; the *explanation* was argued over for 80+ years. Say so on slide 4.
**Why it matters** — No refrigerant, no electricity, no moving parts, no maintenance. Used for spot-cooling machine tools today. Energy separation comes from work transfer between inner and outer vortex, not a thermodynamic loophole.
**The catch** — Efficiency is poor; worth it only where compressed air already exists and reliability beats efficiency. A magnet for perpetual-motion misreadings — compressing the air upstream is where the work went.

### 5 · 8.25 · `orbit` — Falling into the Sun is the hard part

**Hook** — Leaving the solar system takes less fuel than falling into the Sun.
**Source** — [Space SE, accepted answer](https://space.stackexchange.com/questions/45617/why-is-it-easier-to-escape-the-solar-system-than-get-to-mercury-or-the-sun) · **attribute to** the vis-viva result or a NASA Parker Solar Probe mission page.
**Settled?** Textbook-settled orbital mechanics.
**Why it matters** — Earth carries you sideways at 29.78 km/s. Escaping the Sun costs about 16.6 km/s more; *stopping* costs nearly the full 29.78. Every sunward probe pays this in years of gravity assists instead of fuel.
**The catch** — "Easier" means delta-v, not time or difficulty. Nobody actually cancels 29.78 km/s — real missions cheat with flybys, which is why BepiColombo needed nine.

### 6 · 8.00 · `ember` — Clean metal welds itself

**Hook** — Two clean pieces of the same metal touched together in vacuum fuse into one piece, permanently.
**Source** — ESA, *Assessment of Cold Welding between Separable Contact Surfaces*, STM-279, 2009 (ISBN 978-92-9221-900-0) — use this as `source_url`. Explanation scaffold: [Physics SE](https://physics.stackexchange.com/questions/87107/why-dont-metals-bond-when-touched-together), [Cold welding](https://en.wikipedia.org/wiki/Cold_welding).
**Settled?** Textbook-settled and operationally critical to spacecraft design.
**Why it matters** — The only reason your hands do not weld to a doorknob is contamination: oxide layers, grease, adsorbed water. The atoms genuinely cannot tell which block they belong to. Remove the air and the distinction disappears — which is why Galileo's high-gain antenna never fully opened in 1991.
**The catch** — Needs clean, flat, similar metals and real contact pressure. In orbit it tangles with galling and fretting, so "cold welding" in an anomaly report is often a mixed mechanism.

### 7 · 8.00 · `bloom` — No vertebrate makes blue

**Hook** — No vertebrate on Earth can make a blue pigment. Every blue animal you have seen is an optical trick.
**Source** — [Biology SE](https://biology.stackexchange.com/questions/56476/why-are-so-few-foods-blue) · **draft by hand** from its cited primaries; the structural-colour claim needs a real optics citation.
**Settled?** Settled for animals. *Why* blue pigments are so rare is explicitly unknown.
**Why it matters** — Grind up a *Morpho* wing and the blue vanishes; the dust is grey-brown. Colour there is nanostructure, not chemistry — the same physics as soap films. In plants the few real blues come from anthocyanins shifted by pH and metal ions.
**The catch** — "Rare" is not "absent," and the underlying why is open. Do not claim an adaptive explanation the literature has not made.

### 8 · 8.00 · `orbit` — The man who put his head in a particle accelerator

**Hook** — A physicist put his head in a running particle accelerator in 1978 and finished his PhD.
**Source** — [Anatoli Bugorski](https://en.wikipedia.org/wiki/Anatoli_Bugorski) · **chase the primary case report before any number reaches a slide.**
**Settled?** Settled as a documented case; the dose figures (2,000–3,000 Sv) are reconstructions, not measurements.
**Why it matters** — A whole-body dose that size is universally fatal. Bugorski survived because a 76 GeV proton beam is a pencil — it deposits along a narrow track and spares the marrow and gut that actually kill you. The clearest real-world illustration of why dose *distribution* matters more than dose, which is the basis of proton therapy.
**The catch** — He lost the left half of his face to nerve destruction and has had seizures since. Not a "radiation is harmless" story, and the numbers are estimates.

### 9 · 8.00 · `signal` — The quantum benchmark that fell to a laptop

**Hook** — The benchmark problem quantum computers were built to solve just fell to an ordinary computer.
**Source** — arXiv:2601.04621 (Garnet Chan et al., Caltech) — **use the arXiv URL as `source_url`** so `PREPRINT_HOSTS` fires. Coverage: [Quanta](https://www.quantamagazine.org/key-chemistry-question-answered-no-quantum-computer-required-20260529/).
**Settled?** **Preprint** — `peer_reviewed: false`, flag required. Also genuinely contested.
**Why it matters** — Since 2017 the FeMo-cofactor of nitrogenase has been *the* quoted proof that quantum computers are necessary. A classical calculation over 78,000+ plausible electron configurations got the ground-state energy anyway, by exploiting limits on information flow between subsystems. It moves the goalposts on "quantum advantage."
**The catch** — Only the ground state. The reaction pathway, which needs a sequence of intermediates, is untouched. Suess: "We're not even close to achieving the holy grail of this."

### 10 · 8.00 · `ember` — The recipe nobody wrote down

**Hook** — The US built a secret warhead material for 14 years, then forgot how, and spent $92 million relearning it.
**Source** — [Fogbank](https://en.wikipedia.org/wiki/Fogbank) · **attribute to** Sandia SAND2001-0063. Hedging language mandatory.
**Settled?** Settled as documented history from unclassified official sources. The composition remains classified — say that rather than guessing.
**Why it matters** — The best part is the failure mode. The reverse-engineered Fogbank did not work, and the cause was an *impurity* left by the original purification process that had quietly been essential. The recipe was written down; the tacit knowledge was not. The whole argument for process documentation, in one object.
**The catch** — "Aerogel interstage material" is expert inference, not confirmation. The post must not assert the composition.

### 11 · 7.75 · `bloom` — 78 million years, or 18 milliseconds

**Hook** — One enzyme takes a reaction that would need 78 million years and finishes it in 18 milliseconds.
**Source** — Radzicka & Wolfenden, "A proficient enzyme," *Science* 267:90–93, 1995. **Attribution must say Radzicka** — Wolfenden is the one who gets quoted. Background: [OMP decarboxylase](https://en.wikipedia.org/wiki/Orotidine_5%E2%80%B2-phosphate_decarboxylase).
**Settled?** Textbook-settled. The 10^17 rate enhancement is a standard benchmark.
**Why it matters** — It does this with no cofactor, no metal, no prosthetic group — just a few charged residues. The trick is ground-state *destabilisation*: an active-site aspartate carboxyl parked next to the substrate's carboxyl, and the molecule escapes by throwing off CO₂. Catalysis by making the starting material uncomfortable.
**The catch** — 78 million years is an *extrapolated* uncatalysed half-life from high-temperature measurements, not an observation. The exact transition state is still argued over.

### 12 · 7.75 · `ember` — The element nobody has seen

**Hook** — Nobody has ever seen astatine. A visible piece would boil itself away instantly.
**Source** — [Astatine](https://en.wikipedia.org/wiki/Astatine) (Featured Article) · **attribute to** an IUPAC or *Nature Chemistry* element profile.
**Settled?** Textbook-settled. Element 85, most stable isotope At-210 at 8.1 hours.
**Why it matters** — Less than a gram exists in the entire crust at any moment, and only as a decay product. A macroscopic sample would vaporise from its own radioactive self-heating — a property, not a handling problem. The clearest case of an element whose bulk chemistry can only be *inferred*.
**The catch** — Keep "never been seen" precise: its compounds and tracer-scale behaviour are well characterised, and At-211 is in clinical trials for targeted alpha therapy. Rare is not useless.

### 13 · 7.75 · `signal` — Apollo's three-constant sine

**Hook** — The computer that landed Apollo on the Moon calculated sine with three constants and a multiply.
**Source** — [Space SE, accepted answer](https://space.stackexchange.com/questions/30952/how-did-the-apollo-computers-evaluate-transcendental-functions-like-sine-arctan) → primary is the AGC assembly source (`virtualagc`, routines `SPSIN`/`SPCOS`/`POLLEY`). **Attribute to** the MIT Instrumentation Laboratory.
**Settled?** Settled — the source code is public and quoted line by line.
**Why it matters** — No lookup table, no iteration. A truncated Taylor polynomial with coefficients 0.7853134, −0.3216147, 0.0363551 in Horner form, in fixed point, scaled so the argument is in units of π. Accuracy was traded away deliberately to fit the hardware — the opposite of how anyone writes numerics now.
**The catch** — Three terms is good to a few decimal places. That was fine because the sensors feeding it were worse. An engineering-tolerance story, not a clever-algorithm story.

### 14 · 7.50 · `signal` — Chess was easy; picking up a cup was not

**Hook** — Chess was easy for computers. Picking up a cup took another forty years.
**Source** — [Moravec's paradox](https://en.wikipedia.org/wiki/Moravec%27s_paradox) · **draft by hand**; cite Moravec, *Mind Children* (1988) directly.
**Settled?** A settled observation with a *proposed* explanation. The evolutionary account is Moravec's hypothesis, not a demonstrated result.
**Why it matters** — The proposed reason: sensorimotor skill has had a billion years of selection optimising it, abstract reasoning maybe a hundred thousand. What feels effortless is the most heavily engineered thing you own — and being unaware of a process is evidence it works well, not that it is simple.
**The catch** — The paradox is eroding but not gone. Robot manipulation has improved sharply, and this is a 1980s observation about 1980s systems. Treating it as a law is overreach.

### 15 · 7.50 · `ember` — Nine drops in a century

**Hook** — A funnel of tar has dripped nine times since 1927. Nobody has ever watched a drop fall.
**Source** — [Pitch drop experiment](https://en.wikipedia.org/wiki/Pitch_drop_experiment) · **attribute to** Edgeworth, Dalton & Parnell, *Eur. J. Phys.* 5(4):198–200, 1984.
**Settled?** Settled. Viscosity computed from the eighth drop (28 Nov 2000) at roughly 230 billion times that of water.
**Why it matters** — A running argument against your eyes: pitch shatters like glass under a hammer and flows like a liquid over decades. "Solid" and "liquid" are statements about timescale, not substance. The custodian, John Mainstone, watched it for 52 years and missed every drop — once by stepping out for a drink.
**The catch** — Not a controlled experiment. No temperature control until air conditioning arrived after 1988, so measured viscosity drifts seasonally and drop intervals are not comparable. Also: this does *not* mean window glass flows — kill that myth on slide 4.

### 16 · 7.00 · `bloom` — Retracted after fifteen years

**Hook** — *Science* retracted the arsenic-life paper after fifteen years, and the authors still stand by it.
**Source** — [Retraction Watch](https://retractionwatch.com/2025/07/24/science-retraction-arsenic-life-nasa-astrobiology/) → Wolfe-Simon et al., *Science*, December 2010, plus the 2025 retraction notice.
**Settled?** **A retraction** — unusual in being issued with no allegation of fraud or error. See the contract note at the top of this file.
**Why it matters** — The stated technical failure is mundane: nucleic acids "not sufficiently purified before the acquisition of spectra." The interesting part is the policy shift — *Science* can now retract when "a paper's reported experiments do not support its key conclusions, even if no fraud or manipulation occurred." That redefines what retraction means.
**The catch** — The authors dispute it: "we stand by the data as reported," and argue *Science* broke publication-ethics guidelines by retracting absent misconduct. Both positions must appear or the post is unfair.

### 17 · 7.00 · `orbit` — The universe is beige

**Hook** — The average colour of the universe is beige.
**Source** — [Cosmic latte](https://en.wikipedia.org/wiki/Cosmic_latte) · **attribute to** Glazebrook & Baldry 2003.
**Settled?** Settled, with a published correction — the first answer was whiteish green and was wrong.
**Why it matters** — It fell out of a star-formation survey of 200,000+ galaxies, not a colour study. The beige encodes that most stars formed about 5 billion years ago and are now yellowing toward red giants. The universe's colour is a clock.
**The catch** — The weakest explanation on this list, and honestly so: the answer depends entirely on the assumed colour space and white point, which is why the first published value was wrong. The visual carries this post, not the mechanism.

---

## Considered and held

- **Mpemba effect** — physicists are still divided on the *definition*, let alone the mechanism. No claim stable enough for five slides. The Kumar & Bechhoefer *Nature* 2020 colloidal result is a different phenomenon wearing the same name.
- **Google quantum supremacy** — the best available answer is philosophical rather than mechanistic, and the claim has been repeatedly contested by improved classical simulation. Not evergreen.
- **Retraction Watch, September 2026 items** — Ariely procrastination, Oxford "atmospheric thirst", Great Pyramid corridors. These are current news and belong to `ingest.py`, not here.

## Source problem found while compiling

`nature.com/milestones` returns **HTTP 410** and the immersive Milestones pages
redirect through `idp.nature.com` authentication, so nothing was proposed from
that source. It is listed as a Tier 6 evergreen source in
`gummietech_content_system.md` §3 and needs either a replacement URL or removal
from that list.
