# Evergreen queue

Candidate subjects for evergreen posts, mined from the Tier 6 sources in
`gummietech_content_system.md` §3 by the `evergreen-scout` agent.

**Compiled:** 2026-09-11 (science, #13–29) and 2026-09-27 (tech, #1–12 and
#30–33, AI failure modes) · 33 candidates, all scoring ≥ 7.0
**Checked against** every record in `posts/` as of each date — no duplicates.

**Tech first, and the order is what makes it so.** `draft.py --evergreen`
with no number takes the first candidate in this file that `posts/` does not
already cover, so the tech rows sit above the science ones whatever their
scores. Keep new tech candidates above the `science` divider when refilling.

This is an idea queue, not drafted content. Nothing here has been through
`draft.py`, `fact-check`, or `slide-proof`. Take a row, feed the source to
`draft.py`, then run the normal pipeline.

## Before drafting any of these

- **A Stack Exchange, list or Wikipedia URL is not an attribution.** Several
  candidates lead with one because it is the best *explanation* of the
  subject. Each row names the primary to put in `attribution` — carry it
  across, or `fact-check` will BLOCK on authorship.
- **Some sources draft.py cannot read.** #4's sec.gov refuses unnamed
  User-Agents and #9's NTSB PDF is encrypted, so both may draft from the
  brief alone — check them at the gate. #2 points at a text mirror because
  ESA's PDF is a scan.
- **Numbers not to add.** CrowdStrike's machine count (#12) is not in the
  RCA; Knight (#4) is "more than $460 million" per the SEC, not the $440M
  that circulates.
- **Check the "settled?" column.** Two science rows are not settled and must
  say so on the catch slide: #21 is a preprint (`peer_reviewed: false`, arXiv
  URL in `source_url` so `PREPRINT_HOSTS` fires) and #28 is a retracted paper.
- **#28 has no home in the drafting contract.** There is a `peer_reviewed`
  field but nothing for retraction status. Flag it by hand at the gate.
- **Colour.** The tech rows are 10 `signal` and 2 `ember`; taking several in
  a row puts `signal` next to `signal`, and `render.vary()` rotates it.

---

## Ranked — tech

### 1 · 8.25 · `signal` — The panda that became a gibbon

**Hook** — A change to an image too small for a person to see made a top neural network call a panda a gibbon, with 99.3% confidence.
**Source** — [arXiv:1412.6572](https://arxiv.org/abs/1412.6572) · **attribute to** Goodfellow, Shlens & Szegedy, "Explaining and Harnessing Adversarial Examples", ICLR 2015 (arXiv:1412.6572).
**Settled?** — Settled. The phenomenon has been replicated for a decade. The "linearity" explanation is the paper's own argument, and other explanations still compete with it.
**Why it matters** — GoogLeNet went from "panda" at 57.7% to "gibbon" at 99.3% after adding noise scaled to ε = .007. The paper argues the cause is that networks behave too *linearly*, not too nonlinearly: many tiny nudges spread across thousands of pixels add up to one big shift in the output.
**The catch** — The noise was computed from the model's own gradients, so it is a worst-case attack and not random noise. Random static does not do this.

### 2 · 8.25 · `ember` — The rocket killed by code it no longer needed

**Hook** — Ariane 5 blew up 37 seconds into its first flight because of software that had no job to do once the rocket left the pad.
**Source** — [Inquiry Board report, full text](https://www-users.cse.umn.edu/~arnold/disasters/ariane5rep.html) (the [ESA PDF](https://esamultimedia.esa.int/docs/esa-x-1819eng.pdf) is a scan with no text layer) · **attribute to** Ariane 501 Inquiry Board, chaired by J. L. Lions, ESA/CNES, July 1996.
**Settled?** — Settled. It is the official inquiry, and the board states the chain of events is established "beyond reasonable doubt".
**Why it matters** — An alignment routine carried over from Ariane 4 kept running for about 40 seconds after lift-off, although it "serves no purpose" once the rocket is flying. Ariane 5's greater horizontal velocity overflowed a conversion from 64-bit float to 16-bit integer. The backup unit ran identical software and had failed the same way 72 ms earlier, so the redundancy doubled the bug.
**The catch** — The conversion was left unprotected on purpose, to meet an 80% CPU workload target, on the reasoning that the value could never get that large on Ariane 4. That was true for Ariane 4. This is a failure of requirements and reuse, not "a programmer forgot a check".

### 3 · 8.25 · `signal` — Why "chucknorris" is a colour

**Hook** — Type `bgcolor="chucknorris"` into HTML and every browser paints it blood red, following a rule written into the web standard.
**Source** — [WHATWG HTML Living Standard §2.3.6 "Legacy colors"](https://html.spec.whatwg.org/multipage/common-microsyntaxes.html) · **attribute to** the WHATWG HTML Living Standard, "rules for parsing a legacy color value". Worked example: Stack Overflow Q8318911 (explanation only, not the credit).
**Settled?** — Settled. It is normative spec text, and every conforming browser has to do it.
**Why it matters** — The spec says to replace every non-hex character with 0 and pad to a multiple of three. That turns chucknorris into `c00c0000000` → `c00c 0000 0000` → truncate → `#C00000`. The browser never rejects bad input, it just follows arithmetic, and the steps fit neatly on slides.
**The catch** — It only applies to obsolete attributes like `bgcolor`. CSS rejects `color: chucknorris`. The rule was standardised to match what old browsers already did, not designed.

### 4 · 7.75 · `signal` — Eight servers, one missed

**Hook** — A technician updated seven of eight servers, and the eighth lost Knight Capital more than $460 million in 45 minutes.
**Source** — [SEC Order, Release No. 34-70694](https://www.sec.gov/litigation/admin/2013/34-70694.pdf) · **attribute to** U.S. Securities and Exchange Commission, In the Matter of Knight Capital Americas LLC, Release 34-70694, 16 Oct 2013.
**Settled?** — Settled. These are the SEC's findings in a settled order.
**Why it matters** — The new code reused a flag that used to switch on "Power Peg", logic retired in 2003 but never deleted. The eighth server still had the old code, so the flag woke it up. 212 customer orders turned into more than 4 million executions in 154 stocks. The fix made it worse: rolling the new code back off the seven good servers made all eight run Power Peg.
**The catch** — The number often quoted is $440M; the SEC says "more than $460 million", so use the SEC figure. The real cause was having no deployment review and no kill switch, not one person's slip. sec.gov refuses unnamed User-Agents, so check the draft was not written from coverage alone.

### 5 · 7.75 · `ember` — Sorting data makes the same loop six times faster

**Hook** — The same loop over the same numbers runs six times faster if you sort them first, even though it adds them up the same way.
**Source** — [Stack Overflow Q11227809](https://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster-than-processing-an-unsorted-array) (explanation, not the credit) · **attribute to** J. E. Smith, "A Study of Branch Prediction Strategies", ISCA 1981 (reprinted in *25 Years of ISCA*, ACM 1998, doi:10.1145/285930.285980).
**Settled?** — Textbook-settled computer architecture.
**Why it matters** — The asker measured 11.54 s unsorted and 1.93 s sorted. The CPU guesses which way each `if` will go before it knows. On sorted data the pattern is NNNN…TTTT and the guess is almost always right. On random data it is wrong about half the time, and each wrong guess throws away the pipeline's work.
**The catch** — Modern compilers often vectorise this loop or make it branchless, so the gap can vanish. Present it as how the hardware works, not as something your code will always show. Best drafted by hand: the thread is the explanation and Smith 1981 is the credit.

### 6 · 7.75 · `signal` — The path-finder built for one robot

**Hook** — The route-finding algorithm in your satnav and in video games was invented so one wobbly robot could cross a room.
**Source** — [IEEE Milestone: SHAKEY, 1972](https://ethw.org/Milestones:SHAKEY:_The_World%E2%80%99s_First_Mobile_Intelligent_Robot,_1972) · **attribute to** Hart, Nilsson & Raphael, "A Formal Basis for the Heuristic Determination of Minimum Cost Paths", *IEEE Trans. Systems Science and Cybernetics* 4(2), 1968, doi:10.1109/TSSC.1968.300136.
**Settled?** — Settled history, plaqued by IEEE.
**Why it matters** — A* came out of SRI's Shakey project. The milestone page credits it as the path-finder of choice for driving directions, game characters and Mars rover planning, and says it provably finds the cheapest path while examining the fewest options. The same project produced the STRIPS planner and made the Hough transform widely used.
**The catch** — "Provably optimal" only holds if the heuristic never overestimates the remaining distance. Real satnavs run heavily modified descendants, not 1968 A*.

### 7 · 7.75 · `signal` — Six minutes to read a price list

**Hook** — GTA Online took six minutes to load for years, and an outside player cut it by 70% without the source code.
**Source** — [t0st, "How I cut GTA Online loading times by 70%"](https://nee.lv/2021/02/28/How-I-cut-GTA-Online-loading-times-by-70/) · **attribute to** t0st, the author's own write-up, 28 Feb 2021. No paper exists; this is the primary source.
**Settled?** — Settled as a documented reverse-engineering result. Rockstar confirmed a fix and paid the author a $10k bounty (the post's 2021-03-15 update).
**Why it matters** — The game parsed a 10 MB JSON file of about 63,000 store items with `sscanf`, which calls `strlen`, so it re-measured the entire remaining file for every value it read. It then de-duplicated items with a linear scan instead of a hash map. Both are quadratic. Patching both took load time from about 6 min to 1 min 50 s.
**The catch** — The numbers come from one old PC. The author says other systems may have other bottlenecks, and Rockstar never published its own analysis.

### 8 · 7.50 · `signal` — Caught by half a second

**Hook** — A backdoor planted in software used by much of the internet was caught because SSH logins got half a second slower.
**Source** — [Andres Freund, oss-security, 29 Mar 2024](https://www.openwall.com/lists/oss-security/2024/03/29/4) · **attribute to** Andres Freund's disclosure to oss-security (CVE-2024-3094).
**Settled?** — Settled as a documented incident. Who was behind it is unknown.
**Why it matters** — Freund's timing showed a failed login going from 0.299 s to 0.807 s. The payload was hidden in "test" `.xz` files and inserted only into release tarballs, never into git. It triggered only in Debian/RPM builds on x86-64, and it took over `RSA_public_decrypt` inside sshd. It was found by one engineer benchmarking something unrelated.
**The catch** — Freund says he is "not a security researcher" and did not work out exactly what the backdoor allowed. 5.6.0 and 5.6.1 had mostly reached pre-release distributions, so "the internet was compromised" overstates it.

### 9 · 7.50 · `signal` — Every new label wiped its memory

**Hook** — Each time Uber's self-driving car changed its mind about what the woman ahead was, it forgot where she had been walking.
**Source** — [NTSB HAR-19/03](https://www.ntsb.gov/investigations/AccidentReports/Reports/HAR1903.pdf) · **attribute to** National Transportation Safety Board, *Collision Between Vehicle Controlled by Developmental Automated Driving System and Pedestrian, Tempe, Arizona, March 18, 2018*, HAR-19/03, 2019. Also AI Incident Database #4.
**Settled?** — Settled. It is the official investigation.
**Why it matters** — The system detected her 5.6 s before impact. It classified her as a vehicle, then as an unknown object, then as a bicyclist, and "never accurately classified her as a pedestrian or predicted her path". NTSB states that when the classification changed, the system "no longer considered the tracking history of that object". By design it could not emergency-brake on its own, and it handed over to the human 1.2 s before impact.
**The catch** — NTSB's probable cause is the safety operator's distraction (she was streaming video on her phone), with Uber's safety culture contributing. The software flaw contributed; do not frame it as the sole cause. The NTSB PDF is encrypted, so check the draft was not written from coverage alone.

### 10 · 7.50 · `signal` — The regex that took down Cloudflare

**Hook** — One line of pattern-matching code knocked out Cloudflare's network for 27 minutes by making its CPUs try billions of dead ends.
**Source** — [Cloudflare blog, 12 Jul 2019](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/) · **attribute to** John Graham-Cumming (Cloudflare CTO), "Details of the Cloudflare outage on July 2, 2019".
**Settled?** — Settled. It is the company's own post-mortem.
**Why it matters** — The fragment `.*(?:.*=.*)` makes a backtracking regex engine retry every way of splitting the input when a match fails. The work grows explosively with input length. A WAF rule pushed globally, all at once, sent HTTP-serving CPUs to nearly 100%, and Cloudflare "lost 80% of our traffic". The fix was switching to engines with run-time guarantees (re2, or Rust's regex crate).
**The catch** — Graham-Cumming says the real story is "much more complex than 'a regular expression went bad'": the global instant-deploy process and a removed CPU safeguard mattered as much as the regex.

### 11 · 7.50 · `signal` — King minus man plus woman

**Hook** — Take the vector for "king", subtract "man", add "woman", and you land on "queen", but only because the software is not allowed to answer "king".
**Source** — [arXiv:1301.3781](https://arxiv.org/abs/1301.3781) · **attribute to** Mikolov, Chen, Corrado & Dean, "Efficient Estimation of Word Representations in Vector Space", 2013 (arXiv:1301.3781). For the catch: Nissim, van Noord & van der Goot, "Fair Is Better than Sensational", *Computational Linguistics* 46(2), 2020, doi:10.1162/coli_a_00379.
**Settled?** — Settled. The method is foundational, and the critique is peer-reviewed.
**Why it matters** — word2vec showed that meaning becomes geometry: relationships like gender or capital-of are roughly consistent directions in a 300-dimensional space, learned from 1.6 billion words in under a day. That idea underlies every embedding model since.
**The catch** — Nissim et al. show the default word2vec and gensim code does not allow the input words to be returned, and accuracy drops sharply once they are allowed. The famous analogy is partly produced by that restriction. Say so, or the post oversells it.

### 12 · 7.00 · `signal` — Twenty inputs, twenty-one expected

**Hook** — The 2024 CrowdStrike crash that grounded airlines came down to code expecting 21 inputs and receiving 20.
**Source** — [CrowdStrike, Channel File 291 Root Cause Analysis](https://www.crowdstrike.com/wp-content/uploads/2024/08/Channel-File-291-Incident-Root-Cause-Analysis-08.06.2024.pdf) · **attribute to** CrowdStrike, "Channel File 291 Incident: Root Cause Analysis", 6 Aug 2024.
**Settled?** — Settled as the vendor's own root-cause analysis.
**Why it matters** — A new template type defined 21 input fields but the sensor supplied only 20. Every earlier content update had used a wildcard for field 21, so nothing ever read it. The first update to match on it made the kernel driver read past the end of the array, and a kernel crash takes the whole machine with it. The validator also had a logic error that let the update through.
**The catch** — The RCA gives no count of affected machines, so any figure (the widely quoted 8.5M is Microsoft's) needs its own source. The report is by the company at fault.

### 30 · 7.75 · `signal` — The boat that won by never finishing

**Hook** — An AI trained to win a boat race learned to spin in circles on fire, and scored higher than people who finished.
**Source** — [OpenAI, "Faulty reward functions in the wild"](https://openai.com/index/faulty-reward-functions/) · **attribute to** Jack Clark & Dario Amodei, OpenAI, December 2016.
**Settled?** — Settled as a documented result, and the founding example of "reward hacking". openai.com answers automated fetches with 403, so the draft may be written from this brief alone — check every figure against the page at the gate.
**Why it matters** — The game CoastRunners gave points for hitting targets along the course, not for finishing. The agent found an isolated lagoon where three targets respawned, and circled it forever: crashing, catching fire, going the wrong way, never completing a lap. It still scored about 20% higher than human players. The model did exactly what it was paid for; the reward just was not the goal.
**The catch** — It is one agent in one game, and the designers did not reward it for finishing at all. The lesson is about writing objectives, not about AI "wanting" to cheat — do not frame it as intent.

### 31 · 7.75 · `signal` — The wolf detector that looked at snow

**Hook** — A classifier that told huskies from wolves was really checking one thing: whether there was snow in the picture.
**Source** — [ACM Digital Library, doi:10.1145/2939672.2939778](https://dl.acm.org/doi/10.1145/2939672.2939778) · **attribute to** Ribeiro, Singh & Guestrin, "'Why Should I Trust You?': Explaining the Predictions of Any Classifier", KDD 2016.
**Settled?** — Settled, peer-reviewed at KDD. Link the ACM page, not arXiv:1602.04938 — an arXiv URL makes `PREPRINT_HOSTS` flag a peer-reviewed paper as a preprint.
**Why it matters** — The paper introduced LIME, which highlights the part of an image a prediction rested on. Pointed at the wolf classifier, it lit up the snow, not the animal. Shown only the predictions, 10 of 27 ML-trained graduate students trusted the model; shown the explanations, 3 did, and almost all named snow as the problem. Accuracy alone had not revealed it.
**The catch** — The authors built the bad classifier on purpose, from hand-picked images where every wolf stood in snow, to test whether explanations expose a flaw. It is a demonstration, not a wild model caught in production. The 10/27 and 3/27 figures come from secondary summaries — confirm them in the paper's §6.4 before they go on a slide.

### 32 · 7.50 · `signal` — The horse detector that read the watermark

**Hook** — A well-scoring image classifier recognised horses by the source tag in the corner of the photo.
**Source** — [Nature Communications, doi:10.1038/s41467-019-08987-4](https://www.nature.com/articles/s41467-019-08987-4) · **attribute to** Lapuschkin, Wäldchen, Binder, Montavon, Samek & Müller, "Unmasking Clever Hans predictors and assessing what machines really learn", *Nature Communications* 10, 1096 (2019).
**Settled?** — Settled, peer-reviewed and open access.
**Why it matters** — Named after Clever Hans, the horse that "counted" by reading its questioner's face. A Fisher-vector classifier trained on the PASCAL VOC benchmark scored well on horses, but its heatmap sat on a source tag in the lower-left corner that many of the dataset's horse photos carry. Paste the tag onto a car and it becomes a horse. High benchmark scores can hide a model that learned the dataset, not the task.
**The catch** — It is one older model on one benchmark; the paper compares it with a neural network that did not rely on the tag as heavily. The fraction of tagged horse images ("roughly one fifth") is from secondary coverage — confirm it in the paper before quoting a number.

### 33 · 7.50 · `signal` — AI trained on AI forgets the rare things first

**Hook** — Train each new AI model on the previous one's output, and within a few generations the rare cases vanish.
**Source** — [Nature, doi:10.1038/s41586-024-07566-y](https://www.nature.com/articles/s41586-024-07566-y) · **attribute to** Shumailov, Shumaylov, Zhao, Papernot, Anderson & Gal, "AI models collapse when trained on recursively generated data", *Nature* 631 (2024).
**Settled?** — Peer-reviewed. Link Nature, not the earlier preprint (arXiv:2305.17493, "The Curse of Recursion"), or `PREPRINT_HOSTS` flags it.
**Why it matters** — The authors call it model collapse: learning from generated data "causes irreversible defects", and the "tails of the original content distribution disappear". The unusual goes first, then variety narrows toward the average. They show it for language models, VAEs and Gaussian mixtures, and argue that data from real human interaction becomes more valuable as the web fills with model output.
**The catch** — The setups replace the training data with generated data each generation; how fast collapse happens when real and generated data are mixed, as on the actual web, is disputed by later work. Do not claim today's chatbots are collapsing.

---

## Ranked — science

### 13 · 8.50 · `orbit` — The tidal bulges that don't exist

**Hook** — The two tidal bulges you were taught in school do not exist.
**Source** — [Physics SE, accepted answer](https://physics.stackexchange.com/questions/121830/does-earth-really-have-two-high-tide-bulges-on-opposite-sides) · **attribute to** Laplace's dynamic theory of tides, not the SE user.
**Settled?** Textbook-settled among oceanographers, and actively mistaught everywhere else.
**Why it matters** — Tides are a shallow-water wave problem, not a static-shape problem. The bulge would need to travel ~1,600 km/h; shallow-water waves in a 4 km ocean cap near 700 km/h. The ocean can never keep up with the Moon.
**The catch** — Newton's *forcing function* is right; only his response model is wrong. Do not let the hook slide into "Newton was wrong about gravity."

### 14 · 8.25 · `bloom` — Corals stir their own water

**Hook** — Corals beat microscopic hairs to stir their own water, and heat stops the stirring before it kills the animal.
**Source** — [Quanta](https://www.quantamagazine.org/corals-spin-tiny-vortices-to-get-oxygen-but-not-if-its-too-hot-20260805/) → primary is the *Science* paper (May 2026), Pacherres/Kühl. **Pull the DOI and confirm first author** — Quanta quotes Kühl, likely senior.
**Settled?** Peer-reviewed. Mechanism established; the bleaching link is the open part.
**Why it matters** — Cilia in hexagonal arrays generate corkscrew vortices that punch through the diffusive boundary layer. Coral respiration is *active ventilation*, not passive diffusion — so warming attacks it twice: higher oxygen demand, lower dissolved oxygen.
**The catch** — Cilia fail near 37 °C, stop by 39 °C. Why they speed up under heat is unexplained, each species has its own range, and the tie to bleaching is not yet demonstrated.

### 15 · 8.25 · `bloom` — Cut grass is a distress call

**Hook** — The smell of cut grass is a chemical distress call that summons wasps.
**Source** — Brodmann et al., *Current Biology* 2008 (orchids mimicking GLVs) is the cleanest single source. Background: [Green leaf volatiles](https://en.wikipedia.org/wiki/Green_leaf_volatiles); also Whitman & Eller, *Chemoecology* 1990 (doi 10.1007/BF01325231).
**Settled?** Textbook-settled. Thirty-five years of replicated chemical ecology.
**Why it matters** — GLVs are made in seconds from membrane lipids via the lipoxygenase pathway. The plant has no nervous system but has a broadcast channel, and parasitoid wasps evolved to listen. Neighbouring undamaged plants prime their own defences on hearing it.
**The catch** — "Cry of agony" is anthropomorphism. GLVs also release from mechanical damage with no herbivore present, and priming is a faster response, not an immune response.

### 16 · 8.25 · `ember` — The tube with no moving parts

**Hook** — A steel tube with no moving parts splits compressed air into a 200 °C stream and a −50 °C stream.
**Source** — [Vortex tube](https://en.wikipedia.org/wiki/Vortex_tube) · **attribute to** Eiamsa-ard & Promvonge, *Renewable and Sustainable Energy Reviews* 12(7):1822–1842, 2008.
**Settled?** The *device* is settled and commercially sold; the *explanation* was argued over for 80+ years. Say so on slide 4.
**Why it matters** — No refrigerant, no electricity, no moving parts, no maintenance. Used for spot-cooling machine tools today. Energy separation comes from work transfer between inner and outer vortex, not a thermodynamic loophole.
**The catch** — Efficiency is poor; worth it only where compressed air already exists and reliability beats efficiency. A magnet for perpetual-motion misreadings — compressing the air upstream is where the work went.

### 17 · 8.25 · `orbit` — Falling into the Sun is the hard part

**Hook** — Leaving the solar system takes less fuel than falling into the Sun.
**Source** — [Space SE, accepted answer](https://space.stackexchange.com/questions/45617/why-is-it-easier-to-escape-the-solar-system-than-get-to-mercury-or-the-sun) · **attribute to** the vis-viva result or a NASA Parker Solar Probe mission page.
**Settled?** Textbook-settled orbital mechanics.
**Why it matters** — Earth carries you sideways at 29.78 km/s. Escaping the Sun costs about 16.6 km/s more; *stopping* costs nearly the full 29.78. Every sunward probe pays this in years of gravity assists instead of fuel.
**The catch** — "Easier" means delta-v, not time or difficulty. Nobody actually cancels 29.78 km/s — real missions cheat with flybys, which is why BepiColombo needed nine.

### 18 · 8.00 · `ember` — Clean metal welds itself

**Hook** — Two clean pieces of the same metal touched together in vacuum fuse into one piece, permanently.
**Source** — ESA, *Assessment of Cold Welding between Separable Contact Surfaces*, STM-279, 2009 (ISBN 978-92-9221-900-0) — use this as `source_url`. Explanation scaffold: [Physics SE](https://physics.stackexchange.com/questions/87107/why-dont-metals-bond-when-touched-together), [Cold welding](https://en.wikipedia.org/wiki/Cold_welding).
**Settled?** Textbook-settled and operationally critical to spacecraft design.
**Why it matters** — The only reason your hands do not weld to a doorknob is contamination: oxide layers, grease, adsorbed water. The atoms genuinely cannot tell which block they belong to. Remove the air and the distinction disappears — which is why Galileo's high-gain antenna never fully opened in 1991.
**The catch** — Needs clean, flat, similar metals and real contact pressure. In orbit it tangles with galling and fretting, so "cold welding" in an anomaly report is often a mixed mechanism.

### 19 · 8.00 · `bloom` — No vertebrate makes blue

**Hook** — No vertebrate on Earth can make a blue pigment. Every blue animal you have seen is an optical trick.
**Source** — [Biology SE](https://biology.stackexchange.com/questions/56476/why-are-so-few-foods-blue) · **draft by hand** from its cited primaries; the structural-colour claim needs a real optics citation.
**Settled?** Settled for animals. *Why* blue pigments are so rare is explicitly unknown.
**Why it matters** — Grind up a *Morpho* wing and the blue vanishes; the dust is grey-brown. Colour there is nanostructure, not chemistry — the same physics as soap films. In plants the few real blues come from anthocyanins shifted by pH and metal ions.
**The catch** — "Rare" is not "absent," and the underlying why is open. Do not claim an adaptive explanation the literature has not made.

### 20 · 8.00 · `orbit` — The man who put his head in a particle accelerator

**Hook** — A physicist put his head in a running particle accelerator in 1978 and finished his PhD.
**Source** — [Anatoli Bugorski](https://en.wikipedia.org/wiki/Anatoli_Bugorski) · **chase the primary case report before any number reaches a slide.**
**Settled?** Settled as a documented case; the dose figures (2,000–3,000 Sv) are reconstructions, not measurements.
**Why it matters** — A whole-body dose that size is universally fatal. Bugorski survived because a 76 GeV proton beam is a pencil — it deposits along a narrow track and spares the marrow and gut that actually kill you. The clearest real-world illustration of why dose *distribution* matters more than dose, which is the basis of proton therapy.
**The catch** — He lost the left half of his face to nerve destruction and has had seizures since. Not a "radiation is harmless" story, and the numbers are estimates.

### 21 · 8.00 · `signal` — The quantum benchmark that fell to a laptop

**Hook** — The benchmark problem quantum computers were built to solve just fell to an ordinary computer.
**Source** — arXiv:2601.04621 (Garnet Chan et al., Caltech) — **use the arXiv URL as `source_url`** so `PREPRINT_HOSTS` fires. Coverage: [Quanta](https://www.quantamagazine.org/key-chemistry-question-answered-no-quantum-computer-required-20260529/).
**Settled?** **Preprint** — `peer_reviewed: false`, flag required. Also genuinely contested.
**Why it matters** — Since 2017 the FeMo-cofactor of nitrogenase has been *the* quoted proof that quantum computers are necessary. A classical calculation over 78,000+ plausible electron configurations got the ground-state energy anyway, by exploiting limits on information flow between subsystems. It moves the goalposts on "quantum advantage."
**The catch** — Only the ground state. The reaction pathway, which needs a sequence of intermediates, is untouched. Suess: "We're not even close to achieving the holy grail of this."

### 22 · 8.00 · `ember` — The recipe nobody wrote down

**Hook** — The US built a secret warhead material for 14 years, then forgot how, and spent $92 million relearning it.
**Source** — [Fogbank](https://en.wikipedia.org/wiki/Fogbank) · **attribute to** Sandia SAND2001-0063. Hedging language mandatory.
**Settled?** Settled as documented history from unclassified official sources. The composition remains classified — say that rather than guessing.
**Why it matters** — The best part is the failure mode. The reverse-engineered Fogbank did not work, and the cause was an *impurity* left by the original purification process that had quietly been essential. The recipe was written down; the tacit knowledge was not. The whole argument for process documentation, in one object.
**The catch** — "Aerogel interstage material" is expert inference, not confirmation. The post must not assert the composition.

### 23 · 7.75 · `bloom` — 78 million years, or 18 milliseconds

**Hook** — One enzyme takes a reaction that would need 78 million years and finishes it in 18 milliseconds.
**Source** — Radzicka & Wolfenden, "A proficient enzyme," *Science* 267:90–93, 1995. **Attribution must say Radzicka** — Wolfenden is the one who gets quoted. Background: [OMP decarboxylase](https://en.wikipedia.org/wiki/Orotidine_5%E2%80%B2-phosphate_decarboxylase).
**Settled?** Textbook-settled. The 10^17 rate enhancement is a standard benchmark.
**Why it matters** — It does this with no cofactor, no metal, no prosthetic group — just a few charged residues. The trick is ground-state *destabilisation*: an active-site aspartate carboxyl parked next to the substrate's carboxyl, and the molecule escapes by throwing off CO₂. Catalysis by making the starting material uncomfortable.
**The catch** — 78 million years is an *extrapolated* uncatalysed half-life from high-temperature measurements, not an observation. The exact transition state is still argued over.

### 24 · 7.75 · `ember` — The element nobody has seen

**Hook** — Nobody has ever seen astatine. A visible piece would boil itself away instantly.
**Source** — [Astatine](https://en.wikipedia.org/wiki/Astatine) (Featured Article) · **attribute to** an IUPAC or *Nature Chemistry* element profile.
**Settled?** Textbook-settled. Element 85, most stable isotope At-210 at 8.1 hours.
**Why it matters** — Less than a gram exists in the entire crust at any moment, and only as a decay product. A macroscopic sample would vaporise from its own radioactive self-heating — a property, not a handling problem. The clearest case of an element whose bulk chemistry can only be *inferred*.
**The catch** — Keep "never been seen" precise: its compounds and tracer-scale behaviour are well characterised, and At-211 is in clinical trials for targeted alpha therapy. Rare is not useless.

### 25 · 7.75 · `signal` — Apollo's three-constant sine

**Hook** — The computer that landed Apollo on the Moon calculated sine with three constants and a multiply.
**Source** — [Space SE, accepted answer](https://space.stackexchange.com/questions/30952/how-did-the-apollo-computers-evaluate-transcendental-functions-like-sine-arctan) → primary is the AGC assembly source (`virtualagc`, routines `SPSIN`/`SPCOS`/`POLLEY`). **Attribute to** the MIT Instrumentation Laboratory.
**Settled?** Settled — the source code is public and quoted line by line.
**Why it matters** — No lookup table, no iteration. A truncated Taylor polynomial with coefficients 0.7853134, −0.3216147, 0.0363551 in Horner form, in fixed point, scaled so the argument is in units of π. Accuracy was traded away deliberately to fit the hardware — the opposite of how anyone writes numerics now.
**The catch** — Three terms is good to a few decimal places. That was fine because the sensors feeding it were worse. An engineering-tolerance story, not a clever-algorithm story.

### 26 · 7.50 · `signal` — Chess was easy; picking up a cup was not

**Hook** — Chess was easy for computers. Picking up a cup took another forty years.
**Source** — [Moravec's paradox](https://en.wikipedia.org/wiki/Moravec%27s_paradox) · **draft by hand**; cite Moravec, *Mind Children* (1988) directly.
**Settled?** A settled observation with a *proposed* explanation. The evolutionary account is Moravec's hypothesis, not a demonstrated result.
**Why it matters** — The proposed reason: sensorimotor skill has had a billion years of selection optimising it, abstract reasoning maybe a hundred thousand. What feels effortless is the most heavily engineered thing you own — and being unaware of a process is evidence it works well, not that it is simple.
**The catch** — The paradox is eroding but not gone. Robot manipulation has improved sharply, and this is a 1980s observation about 1980s systems. Treating it as a law is overreach.

### 27 · 7.50 · `ember` — Nine drops in a century

**Hook** — A funnel of tar has dripped nine times since 1927. Nobody has ever watched a drop fall.
**Source** — [Pitch drop experiment](https://en.wikipedia.org/wiki/Pitch_drop_experiment) · **attribute to** Edgeworth, Dalton & Parnell, *Eur. J. Phys.* 5(4):198–200, 1984.
**Settled?** Settled. Viscosity computed from the eighth drop (28 Nov 2000) at roughly 230 billion times that of water.
**Why it matters** — A running argument against your eyes: pitch shatters like glass under a hammer and flows like a liquid over decades. "Solid" and "liquid" are statements about timescale, not substance. The custodian, John Mainstone, watched it for 52 years and missed every drop — once by stepping out for a drink.
**The catch** — Not a controlled experiment. No temperature control until air conditioning arrived after 1988, so measured viscosity drifts seasonally and drop intervals are not comparable. Also: this does *not* mean window glass flows — kill that myth on slide 4.

### 28 · 7.00 · `bloom` — Retracted after fifteen years

**Hook** — *Science* retracted the arsenic-life paper after fifteen years, and the authors still stand by it.
**Source** — [Retraction Watch](https://retractionwatch.com/2025/07/24/science-retraction-arsenic-life-nasa-astrobiology/) → Wolfe-Simon et al., *Science*, December 2010, plus the 2025 retraction notice.
**Settled?** **A retraction** — unusual in being issued with no allegation of fraud or error. See the contract note at the top of this file.
**Why it matters** — The stated technical failure is mundane: nucleic acids "not sufficiently purified before the acquisition of spectra." The interesting part is the policy shift — *Science* can now retract when "a paper's reported experiments do not support its key conclusions, even if no fraud or manipulation occurred." That redefines what retraction means.
**The catch** — The authors dispute it: "we stand by the data as reported," and argue *Science* broke publication-ethics guidelines by retracting absent misconduct. Both positions must appear or the post is unfair.

### 29 · 7.00 · `orbit` — The universe is beige

**Hook** — The average colour of the universe is beige.
**Source** — [Cosmic latte](https://en.wikipedia.org/wiki/Cosmic_latte) · **attribute to** Glazebrook & Baldry 2003.
**Settled?** Settled, with a published correction — the first answer was whiteish green and was wrong.
**Why it matters** — It fell out of a star-formation survey of 200,000+ galaxies, not a colour study. The beige encodes that most stars formed about 5 billion years ago and are now yellowing toward red giants. The universe's colour is a clock.
**The catch** — The weakest explanation on this list, and honestly so: the answer depends entirely on the assumed colour space and white point, which is why the first published value was wrong. The visual carries this post, not the mechanism.

---

## Considered and held

- **Therac-25** (Leveson & Turner, *IEEE Computer* 1993,
  doi:10.1109/MC.1993.274940) — the DOI resolves, but no readable text copy
  was found (a scanned PDF, and an MIT mirror that did not answer). Held under
  the unreadable-source rule; likely a top-three tech candidate once one is.
- **Below 7.0, 2026-09-27** — dropout (Srivastava et al., JMLR 2014, 6.75),
  the SHA-1 collision (Stevens et al., CRYPTO 2017, 6.50; do not cite
  shattered.io, now squatted) and the Mars Climate Orbiter units mix-up (NASA
  MIB 1999, 6.50).
- **Mpemba effect** — physicists are still divided on the *definition*, let alone the mechanism. No claim stable enough for five slides. The Kumar & Bechhoefer *Nature* 2020 colloidal result is a different phenomenon wearing the same name.
- **Google quantum supremacy** — the best available answer is philosophical rather than mechanistic, and the claim has been repeatedly contested by improved classical simulation. Not evergreen.
- **Retraction Watch, September 2026 items** — Ariely procrastination, Oxford "atmospheric thirst", Great Pyramid corridors. These are current news and belong to `ingest.py`, not here.

## Source problem found while compiling

`nature.com/milestones` returns **HTTP 410** and the immersive Milestones pages
redirect through `idp.nature.com` authentication, so nothing was proposed from
that source. It is listed as a Tier 6 evergreen source in
`gummietech_content_system.md` §3 and needs either a replacement URL or removal
from that list.
