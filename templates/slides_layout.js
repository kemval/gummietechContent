// The slides' layout pass, shared by every format: measurement only, never text. Everything here
// reads the rendered glyphs and moves or scales boxes; the words were all
// placed by the template from the record. render.open_page() waits for
// window.__ready, so a screenshot or a proof never sees a half-laid page.
window.__ready = false;
document.fonts.ready.then(() => {
  const COLUMN = 960;   // frame width 1012 minus 26px each side

  // Scale an element's font until its width is `width`, capped at `maxPx`
  // so a two-character value ("3×") does not become a wall.
  const fit = (el, width, maxPx) => {
    el.style.fontSize = '100px';
    for (let i = 0; i < 3; i++) {   // twice more: tracking is not linear in size
      const w = el.offsetWidth;     // layout pixels, unaffected by the reel's scale
      el.style.fontSize = Math.min(maxPx, parseFloat(el.style.fontSize) * width / w).toFixed(2) + 'px';
    }
  };

  try {
  // Slides with a frame only: the reel's full-bleed backdrops carry the
  // `slide` class to resolve their field colour and have nothing to lay out.
  document.querySelectorAll('.slide').forEach(slide => {
    if (!slide.querySelector('.frame')) return;
    // The reel shows these slides in a card scaled to 0.9, and
    // getBoundingClientRect() reports scaled pixels; every measurement is
    // divided back into the slide's own 1080-wide CSS pixels.
    const k = slide.getBoundingClientRect().width / slide.offsetWidth;
    const frame = slide.querySelector('.frame');
    const F = frame.getBoundingClientRect();
    const Fh = F.height / k;
    const top = el => (el.getBoundingClientRect().top - F.top) / k;
    const bottom = el => (el.getBoundingClientRect().bottom - F.top) / k;

    // Ghost words and the wordmark fill the column from their anchor.
    slide.querySelectorAll('.giant[data-anchor]').forEach(g => {
      fit(g, COLUMN, +g.dataset.max || 520);   // data-max caps a short one ("01")
      if (g.dataset.anchor === 'top') {
        const flag = slide.querySelector('.flag-row');   // below the preprint flag, never behind it
        g.style.top = (flag ? bottom(flag) + 24 : +(g.dataset.top || 86)) + 'px';
      }
      else {
        // below whatever text sits above it, and never past the corner labels
        const above = slide.querySelector('.body.top');
        g.style.bottom = '60px';
        if (above && top(g) < bottom(above) + 40) fit(g, COLUMN * (Fh - 60 - bottom(above) - 40) / g.offsetHeight, 520);
      }
    });

    // The cover: the spec row docks above the figure, or takes the bottom
    // margin when there is none, and the hook is sized to clear it.
    const hook = slide.querySelector('.hook'), spec = slide.querySelector('.spec');
    if (hook && spec) {
      const figure = slide.querySelector('.figure');
      // Clear of the spec row, and nothing in the hook wider than the hook:
      // a boxed phrase cannot wrap, so a long one ("Decorrelation stretch")
      // is what limits how large the hook can go.
      const fits = () => hook.scrollWidth <= hook.clientWidth &&
        [...hook.querySelectorAll('.sel')].every(s => s.getBoundingClientRect().right <= hook.getBoundingClientRect().right);
      const clears = () => bottom(hook) + 40 <= top(spec) && fits();
      if (figure) {
        const g = figure.querySelector('.giant'), q = figure.querySelector('.qual');
        fit(g, COLUMN - q.offsetWidth - 28, 440);
        for (let k = 0; k < 20; k++) {
          spec.style.bottom = (Fh - top(figure) + 44) + 'px';
          if (clears()) break;
          g.style.fontSize = (parseFloat(g.style.fontSize) * .9) + 'px';
        }
      } else {
        // No figure: the hook is the cover, so it grows into the space
        // (96px up to 176px) and steps down only if it would reach the spec.
        let px = 96;
        while (px < 176) { hook.style.fontSize = (px + 4) + 'px'; if (!clears()) break; px += 4; }
        hook.style.fontSize = px + 'px';
        while (!clears() && px > 64) { px -= 4; hook.style.fontSize = px + 'px'; }
      }
      // With or without a figure, a boxed phrase wider than the column
      // steps the hook down until it fits.
      for (let px = parseFloat(getComputedStyle(hook).fontSize); !fits() && px > 64; ) {
        px -= 4; hook.style.fontSize = px + 'px';
      }
    }

    // The keyword cloud: the post's keywords scattered above the body,
    // sharp and never overlapping one another. Seeded from the hook, so a
    // re-render of the same post is the same picture.
    const cloud = slide.querySelector('.cloud');
    if (cloud) {
      let seed = [...cloud.dataset.seed].reduce((h, c) => Math.imul(h ^ c.charCodeAt(0), 16777619), 2166136261);
      const r = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
      const gauss = () => Math.sqrt(-2 * Math.log(r() + 1e-9)) * Math.cos(2 * Math.PI * r());
      const words = cloud.dataset.words.split('|').filter(Boolean);
      const body = slide.querySelector('.body');
      const floor = top(body) - 60;                   // the cloud stops 60px above the text
      const placed = [];
      for (let i = 0; i < 40 && words.length; i++) {
        const s = document.createElement('span');
        s.textContent = words[i % words.length];
        s.style.fontSize = [18, 20, 22, 26, 30, 38, 48][Math.floor(r() * 7)] + 'px';
        s.style.opacity = (.35 + r() * .65).toFixed(2);
        cloud.appendChild(s);
        const w = s.offsetWidth, h = s.offsetHeight;
        let x = Math.min(Math.max(506 + gauss() * 230 - w / 2, 26), 986 - w);
        let y = Math.min(Math.max(96 + (floor - 96) / 2 + gauss() * (floor - 96) / 4, 96), floor - h);
        const hits = (x, y) => placed.some(p => x < p.x + p.w + 16 && p.x < x + w + 16 && y < p.y + p.h + 4 && p.y < y + h + 4);
        for (let k = 0; hits(x, y) && k < 60; k++) { x = 26 + ((x - 26 + 113) % Math.max(1, 960 - w)); if (k % 7 === 6) y = Math.min(floor - h, y + h); }
        if (hits(x, y) || w > 960) { s.remove(); continue; }
        placed.push({ x, y, w, h }); s.style.left = x + 'px'; s.style.top = y + 'px';
      }
    }
  });
  } catch (e) {
    // Reported, not swallowed: render.open_page() raises with this message
    // rather than screenshotting a half-laid page.
    window.__layoutError = String(e && e.stack || e);
  }
  window.__ready = true;
});
