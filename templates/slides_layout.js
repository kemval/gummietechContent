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

    // Body text grows into a slide's empty space (60px up to 92px) while
    // the body stays under half the frame, so a short field does not
    // leave a dead half-slide. First, because the ghost words below are
    // placed against the text's final size. The diff's smaller catch text is left alone.
    slide.querySelectorAll('.body .text:not(.sm):not(.display)').forEach(t => {
      const body = t.closest('.body');
      let px = parseFloat(getComputedStyle(t).fontSize);
      while (px < 92) { t.style.fontSize = (px + 2) + 'px'; if (body.offsetHeight > Fh * .5) break; px += 2; }
      t.style.fontSize = px + 'px';
    });

    // Ghost words and the wordmark fill the column from their anchor.
    slide.querySelectorAll('.giant[data-anchor]').forEach(g => {
      fit(g, COLUMN, +g.dataset.max || 520);   // data-max caps a short one ("01")
      if (g.dataset.anchor === 'top') {
        const flag = slide.querySelector('.flag-row');   // below the preprint flag, never behind it
        g.style.top = (flag ? bottom(flag) + 24 : +(g.dataset.top || 86)) + 'px';
        // and clear of the body's section rule below it: the body grows
        // upward, and parentheses hang ~.22em under the line box
        const below = slide.querySelector('.body:not(.top)');
        if (below) {
          const ink = () => g.offsetHeight + parseFloat(g.style.fontSize) * .22;
          const room = top(below) - 40 - top(g);
          if (ink() > room) fit(g, g.offsetWidth * room / ink(), 520);
        }
      }
      else {
        // below whatever text sits above it, and never past the corner labels
        const above = slide.querySelector('.body.top');
        // clear of the footer band (rule at y 1240) and its corner labels:
        // parentheses and descenders hang ~.22em below the line box
        const lift = () => { g.style.bottom = (106 + parseFloat(g.style.fontSize) * .22).toFixed(0) + 'px'; };
        lift();
        // too tall for the gap under the text: shrink, re-lift, and repeat,
        // since the lift itself grows with the size
        for (let i = 0; i < 6 && above && top(g) < bottom(above) + 40; i++) {
          const room = Fh - parseFloat(g.style.bottom) - bottom(above) - 40;
          fit(g, g.offsetWidth * room / g.offsetHeight, 520); lift();   // its own width: a capped short word ("1/2") never fills the column
        }
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

    // The keyword callouts (v3, after the owner's 01.tech reference): each
    // keyword in a ruled tag, wired to a dot on the section rule below.
    // Left tags wire in at columns stepping outward as they go down, right
    // tags likewise, so no wire crosses a tag or another wire.
    const cloud = slide.querySelector('.cloud');
    if (cloud) {
      const words = [...new Set(cloud.dataset.words.split('|').filter(Boolean))].slice(0, 4);
      const body = slide.querySelector('.body');
      const floor = top(body), roof = 150;
      const band = (floor - 60 - roof) / Math.max(words.length, 1);
      const add = (cls, css) => { const e = document.createElement('div'); e.className = cls; Object.assign(e.style, css); cloud.appendChild(e); return e; };
      let li = 0, ri = 0;
      words.forEach((w, i) => {
        const t = add('tag', {});
        t.innerHTML = '<i></i>'; t.firstChild.textContent = '(' + String(i + 1).padStart(2, '0') + ')';
        t.appendChild(document.createTextNode(w));
        if (t.offsetWidth > 440) t.style.fontSize = (44 * 440 / t.offsetWidth).toFixed(1) + 'px';
        const left = i % 2 === 0, tw = t.offsetWidth, th = t.offsetHeight;
        const x = left ? 60 + (i % 4 === 2 ? 60 : 0) : 1020 - tw - (i % 4 === 3 ? 60 : 0);
        const y = roof + band * i + (band - th) / 2 + 34;
        t.style.left = (x - 34) + 'px'; t.style.top = (y - 34) + 'px';
        const col = left ? 526 - 30 * li++ : 554 + 30 * ri++;   // frame coords
        const mid = y + th / 2;
        const hx = left ? x + tw : col, hw = left ? col - x - tw : x - col;
        add('wire', { left: (hx - 34) + 'px', top: (mid - 34 - 1) + 'px', width: hw + 'px', borderTopWidth: '2px' });
        add('wire', { left: (col - 34 - 1) + 'px', top: (mid - 34) + 'px', height: (floor - (mid - 34)) + 'px', borderLeftWidth: '2px' });
        add('dot', { left: (col - 34 - 7) + 'px', top: (floor - 7) + 'px' });
      });
    }
  });
  } catch (e) {
    // Reported, not swallowed: render.open_page() raises with this message
    // rather than screenshotting a half-laid page.
    window.__layoutError = String(e && e.stack || e);
  }
  window.__ready = true;
});
