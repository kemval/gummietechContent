// The slides' layout pass, shared by every format: measurement only, never text. Everything here
// reads the rendered glyphs and moves or scales boxes; the words were all
// placed by the template from the record. render.open_page() waits for
// window.__ready, so a screenshot or a proof never sees a half-laid page.
window.__ready = false;
{% include 'backdrop.js' %}
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
  // The slides' use of the moving backdrop (backdrop.js). A slide takes the
  // ribbons of its field; the glass ghost words, the reel's scene mapping and
  // "repaint only what shows" are the slides' own business, so they live here.
  // window.__backdrop(ms) redraws at a moment of the loop: render.py stills
  // are t = 0, and the videos step it frame by frame.
  const R = window.Ribbons;
  const backdrop = (() => {
    if (!R) return null;                        // no WebGL: flat fields, as before
    const all = [];
    const title = (document.querySelector('.hook') || {}).textContent || document.title;
    const FIELDS = ['pink', 'olive', 'sky', 'blush', 'amber', 'cream'];
    // The ghost words ("(why)", "(but)", "1/2"…) as frosted glass: the
    // backdrop blurred and brightened inside the letters, a soft shadow and a
    // bevel edge. CSS cannot clip a blur to glyphs, so they are painted into
    // the backdrop from the DOM element's own font and position (which stays
    // in the page, transparent, for the layout pass and proof).
    const soft = document.createElement('canvas'), softCtx = soft.getContext('2d');
    const layer = document.createElement('canvas'), lctx = layer.getContext('2d');
    const glass = s => {
      // A reel backdrop wears the glass for the content slide of its scene.
      const words = (s.content ? s.content() : s.el).querySelectorAll('.giant.ghost');
      if (!words.length) return;
      const [src, sx, sy, sw, sh] = R.frame(s), c = s.ctx, Wc = c.canvas.width, Hc = c.canvas.height;
      soft.width = sw; soft.height = sh;
      softCtx.filter = 'blur(5px) brightness(1.18) saturate(1.1)';   // blurred small: cheap
      softCtx.drawImage(src, sx, sy, sw, sh, 0, 0, sw, sh);
      softCtx.filter = 'none';
      if (layer.width !== Wc || layer.height !== Hc) { layer.width = Wc; layer.height = Hc; }
      const S = s.el.getBoundingClientRect(), k = S.width / s.el.offsetWidth;
      for (const g of words) {
        const cs = getComputedStyle(g), B = g.getBoundingClientRect(), text = g.textContent;
        const x = (B.left - S.left) / k, top = (B.top - S.top) / k;
        // the word's own scale on screen (the reel's card is 0.9) in host pixels
        const z = B.width / g.offsetWidth / k, px = v => parseFloat(v) * z + 'px';
        const setFont = cx => {
          cx.font = `${cs.fontWeight} ${px(cs.fontSize)} ${cs.fontFamily}`;
          cx.fontStretch = parseFloat(cs.fontStretch) >= 125 ? 'expanded' : 'normal';
          cx.letterSpacing = cs.letterSpacing === 'normal' ? '0px' : px(cs.letterSpacing);
          cx.textBaseline = 'alphabetic';
        };
        setFont(lctx);
        const m = lctx.measureText(text);
        const asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
        // CSS puts the baseline half the leading below the line box's top
        const y = top + (parseFloat(cs.lineHeight) * z - (asc + desc)) / 2 + asc;
        // the glass: the blurred backdrop, kept only inside the letters
        lctx.clearRect(0, 0, Wc, Hc);
        lctx.globalCompositeOperation = 'source-over';
        lctx.fillStyle = '#000'; lctx.fillText(text, x, y);
        lctx.globalCompositeOperation = 'source-in';
        lctx.drawImage(soft, 0, 0, Wc, Hc);
        lctx.fillStyle = s.dark ? 'rgba(255,255,255,.08)' : 'rgba(255,255,255,.22)';
        lctx.fillRect(0, 0, Wc, Hc);
        lctx.globalCompositeOperation = 'source-over';
        c.save();
        c.shadowColor = s.dark ? 'rgba(0,0,0,.45)' : 'rgba(59,44,35,.18)';
        c.shadowBlur = 40; c.shadowOffsetY = 14;
        c.drawImage(layer, 0, 0);
        c.restore();
        // The light edge as a bevel, the letter minus itself shifted: a
        // stroke would also trace the variable font's overlapping contours
        // (a box inside the "t").
        lctx.clearRect(0, 0, Wc, Hc);
        lctx.fillStyle = s.dark ? 'rgba(255,255,255,.35)' : 'rgba(255,255,255,.85)';
        lctx.fillText(text, x, y);
        lctx.globalCompositeOperation = 'destination-out';
        lctx.fillStyle = '#000'; lctx.fillText(text, x + 2.5, y + 2.5);
        lctx.globalCompositeOperation = 'source-over';
        c.drawImage(layer, 0, 0);
      }
    };
    // Without `only`, just what shows. In the reel the slides are stacked,
    // so "on screen" is not enough: walk each stack from the top and stop
    // under the first slide that is opaque and squarely in place.
    const onScreen = el => { const r = el.getBoundingClientRect();
      return r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight; };
    const seen = () => {
      const stacks = new Map(), vis = new Set();
      all.forEach(s => { const p = s.el.parentElement; if (!stacks.has(p)) stacks.set(p, []); stacks.get(p).push(s); });
      stacks.forEach(list => {
        for (let i = list.length - 1; i >= 0; i--) {
          const el = list[i].el, op = parseFloat(getComputedStyle(el).opacity);
          if (!onScreen(el) || op === 0) continue;
          vis.add(list[i]);
          const r = el.getBoundingClientRect(), P = el.parentElement.getBoundingClientRect();
          if (op >= 1 && Math.abs(r.left - P.left) < 1 && Math.abs(r.top - P.top) < 1) break;
        }
      });
      return vis;
    };
    // `only`: true repaints every slide; an element repaints just that one.
    window.__backdrop = (ms, only) => {
      const vis = only ? null : seen();
      all.forEach(s => (only === true || (only ? s.el === only : vis.has(s))) && R.paint(s, ms));
    };
    window.__backdropLoop = R.LOOP;
    return slide => {
      const s = R.attach(slide, {
        field: FIELDS.find(f => slide.classList.contains(f)),
        dark: slide.classList.contains('dark'),
        lead: 'var(--lead)',
        // the reel's returning cover is slide 1 cloned without its id: same seed, no seam
        seed: title + (slide.id || (slide.closest('.loop') ? 'slide-1' : '')),
      });
      if (slide.classList.contains('backdrop')) {
        // backdrop i is scene i: the card's slides, then the returning cover
        const i = [...slide.parentElement.querySelectorAll(':scope > .backdrop')].indexOf(slide);
        s.content = () => document.querySelectorAll('.card > .slide, .card > .loop > .slide')[i] || slide;
      }
      s.after = glass;
      all.push(s);
    };
  })();

  document.querySelectorAll('.slide').forEach(slide => {
    // The reel's full-bleed backdrops carry `slide` for their field colour:
    // they get the moving ribbons too, and have nothing else to lay out.
    if (!slide.querySelector('.frame')) { if (backdrop && slide.classList.contains('backdrop')) backdrop(slide); return; }
    // In the reel the content floats on the full-screen backdrop: its
    // slides draw no background of their own.
    if (backdrop && !slide.closest('.card')) backdrop(slide);
    // The reel shows these slides in a card scaled to 0.9, and
    // getBoundingClientRect() reports scaled pixels; every measurement is
    // divided back into the slide's own 1080-wide CSS pixels.
    const k = slide.getBoundingClientRect().width / slide.offsetWidth;
    const frame = slide.querySelector('.frame');
    const F = frame.getBoundingClientRect();
    const Fh = F.height / k;
    const top = el => (el.getBoundingClientRect().top - F.top) / k;
    const bottom = el => (el.getBoundingClientRect().bottom - F.top) / k;

    // Body text grows into a slide's empty space (60px up to 72px, the scale the owner
    // preferred on 2026-09-28; 92px read as shouting) while
    // the body stays under half the frame, so a short field does not
    // leave a dead half-slide. First, because the ghost words below are
    // placed against the text's final size. The diff's smaller catch text is left alone.
    slide.querySelectorAll('.body .text:not(.sm):not(.display)').forEach(t => {
      const body = t.closest('.body');
      let px = parseFloat(getComputedStyle(t).fontSize);
      while (px < 72) { t.style.fontSize = (px + 2) + 'px'; if (body.offsetHeight > Fh * .5) break; px += 2; }
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
        // (96px up to 120px: past that it shouts over
        // the rest of the post; the owner preferred 2026-09-28's scale) and steps down only if it would reach the spec.
        let px = 96;
        while (px < 120) { hook.style.fontSize = (px + 4) + 'px'; if (!clears()) break; px += 4; }
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
      const add = (cls, css) => { const e = document.createElement('div'); e.className = cls;
        for (const [k, v] of Object.entries(css)) k.startsWith('--') ? e.style.setProperty(k, v) : (e.style[k] = v);
        cloud.appendChild(e); return e; };
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
        // --i and the h/v classes order the reel's entrance (reel.html):
        // the tag, its wire drawn from the tag outward, then down, then the dot.
        t.style.setProperty('--i', i);
        add('wire h', { left: (hx - 34) + 'px', top: (mid - 34 - 1) + 'px', width: hw + 'px', borderTopWidth: '2px',
                        transformOrigin: left ? 'left' : 'right', '--i': i });
        add('wire v', { left: (col - 34 - 1) + 'px', top: (mid - 34) + 'px', height: (floor - (mid - 34)) + 'px', borderLeftWidth: '2px', '--i': i });
        add('dot', { left: (col - 34 - 7) + 'px', top: (floor - 7) + 'px', '--i': i });
      });
    }
  });
  // The first paint ran before the layout pass moved the ghost words; the
  // glass letters are drawn where they ended up.
  if (window.__backdrop) window.__backdrop(0, true);
  } catch (e) {
    // Reported, not swallowed: render.open_page() raises with this message
    // rather than screenshotting a half-laid page.
    window.__layoutError = String(e && e.stack || e);
  }
  window.__ready = true;
});
