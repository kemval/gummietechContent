# The runner pin

Moved verbatim from `CLAUDE.md` on 2026-09-28. `CLAUDE.md` keeps the
rule in a line; this keeps the reasoning and the measurements behind it.
Section names below ("see **X**") refer to `CLAUDE.md`'s headings.

**The runner is pinned to `ubuntu-24.04`, and `ubuntu-latest` is the bug.**
GitHub moves that label to Ubuntu 26.04 *gradually*, between 19 Oct and
19 Nov 2026 (`actions/runner-images#14748`), and gradual is the worst shape
for an unattended pipeline: for a month some runs would take one image and
some the other, so a break would come and go and read as a flake rather than
as a change. The exposure is not Python — `setup-python` pins 3.12 whatever
the image is — it is `playwright install --with-deps chromium` in `check.yml`,
`review.yml` and `site.yml`, which apt-installs a library list that is
per-release, on an image whose kernel and systemd both move (6.17→7.0,
255.4→259.5). Every job carries the label — sixteen on 2026-09-27 — and
Actions gives no way to write it once, so each one says why in a line rather
than leaving bare literals for someone to "modernize" back. Unpin
deliberately — a green `check.yml` on `ubuntu-26.04` first, then every job —
rather than by tidying the comment away.
