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
  // The backdrop (slides.css, "The backdrop"): Neat's technique, our own
  // code. Neat (github.com/FireCMSco/neat) layers colours one over another
  // wherever a horizontally-stretched noise field crosses a threshold,
  // curls the result with cos() flow warps, and lights a waving surface.
  // This does the same in one fragment shader, in the locked palette.
  // One WebGL context serves every slide (a Breakdown has more slides than
  // Chrome allows live contexts); each picture is copied to a 2D canvas.
  // window.__backdrop(ms) redraws them all at a moment in time: render.py
  // stills are t = 0, and the videos step it frame by frame. Time only
  // enters as an angle of one LOOP (noise sampled around a circle), so
  // every clip loops seamlessly.
  const LOOP = 8000;
  const backdrop = (() => {
    const gl = document.createElement('canvas').getContext('webgl', { preserveDrawingBuffer: true });
    if (!gl) return null;                       // flat fields, as before
    // Drawn at a third of the size and scaled up (Neat's renderScale):
    // headless Chrome runs WebGL on the CPU, and at full size a reel took
    // over fifteen minutes. The ribbons are smooth enough not to show it.
    // The GL canvas fits the tallest shape drawn: 4:5 slides and the reel's
    // 9:16 backdrops, each rendered into its own bottom-left viewport.
    const W = 360, H = 450, CH = 640;
    gl.canvas.width = W; gl.canvas.height = CH;
    const src = {
      v: 'attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }',
      f: `precision highp float;
        uniform vec3 C[5]; uniform int N; uniform float seed, a, dark; uniform vec2 res;
        // 3D simplex noise: Ashima Arts / Stefan Gustavson, MIT licence
        vec3 m289(vec3 x){ return x - floor(x*(1./289.))*289.; }
        vec4 m289(vec4 x){ return x - floor(x*(1./289.))*289.; }
        vec4 perm(vec4 x){ return m289(((x*34.)+1.)*x); }
        vec4 tis(vec4 r){ return 1.79284291400159 - .85373472095314*r; }
        float snoise(vec3 v){
          const vec2 C0 = vec2(1./6., 1./3.); const vec4 D = vec4(0., .5, 1., 2.);
          vec3 i = floor(v + dot(v, C0.yyy)); vec3 x0 = v - i + dot(i, C0.xxx);
          vec3 g = step(x0.yzx, x0.xyz); vec3 l = 1. - g;
          vec3 i1 = min(g.xyz, l.zxy); vec3 i2 = max(g.xyz, l.zxy);
          vec3 x1 = x0 - i1 + C0.xxx; vec3 x2 = x0 - i2 + C0.yyy; vec3 x3 = x0 - D.yyy;
          i = m289(i);
          vec4 p = perm(perm(perm(i.z + vec4(0., i1.z, i2.z, 1.)) + i.y + vec4(0., i1.y, i2.y, 1.)) + i.x + vec4(0., i1.x, i2.x, 1.));
          float n_ = .142857142857; vec3 ns = n_*D.wyz - D.xzx;
          vec4 j = p - 49.*floor(p*ns.z*ns.z); vec4 x_ = floor(j*ns.z); vec4 y_ = floor(j - 7.*x_);
          vec4 x = x_*ns.x + ns.yyyy; vec4 y = y_*ns.x + ns.yyyy; vec4 h = 1. - abs(x) - abs(y);
          vec4 b0 = vec4(x.xy, y.xy); vec4 b1 = vec4(x.zw, y.zw);
          vec4 s0 = floor(b0)*2. + 1.; vec4 s1 = floor(b1)*2. + 1.; vec4 sh = -step(h, vec4(0.));
          vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy; vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
          vec3 p0 = vec3(a0.xy, h.x); vec3 p1 = vec3(a0.zw, h.y); vec3 p2 = vec3(a1.xy, h.z); vec3 p3 = vec3(a1.zw, h.w);
          vec4 nm = tis(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
          p0 *= nm.x; p1 *= nm.y; p2 *= nm.z; p3 *= nm.w;
          vec4 m = max(.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.); m = m*m;
          return 42.*dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
        }
        vec2 ring(float r){ return r*vec2(cos(a), sin(a)); }   // one loop = one circle
        float surf(vec2 p){                                    // the waving plane
          vec2 r = ring(.45);   // a smaller circle: the same loop, a slower drift
          return .55*snoise(vec3(p.x*.45, p.y*.55 + r.x, r.y + seed)) + .2*sin(p.x*1.1 + p.y*.7 + a);
        }
        void main(){
          vec2 uv = gl_FragCoord.xy / res; uv.y = 1. - uv.y;
          vec2 p = vec2((uv.x - .5)*3.2, uv.y*3.6*(res.y/res.x)/1.25);   // same ribbon scale at 4:5 and 9:16
          float z = surf(p);
          vec2 q = p + vec2(0., z*.8);                           // colour rides the waves
          q += .12*cos(1.3*q.yx + a + vec2(.1, 1.1));            // Neat's flow curls, one
          q += .09*cos(1.9*q.yx - a + vec2(3.2, 3.4));           // turn per loop each: slow
          q += .06*cos(1.7*q.yx + a + vec2(1.8, 5.2));
          vec2 r = ring(.35);
          vec3 col = C[0];
          for (int i = 1; i < 5; i++) {
            if (i >= N) break;
            float fi = float(i);
            // stretched along x: long horizontal ribbons, like Neat's colour pressure
            float n = snoise(vec3(q.x*.32 + fi*2.3, q.y*.95 + r.x + fi*1.7, r.y + seed + fi*3.1));
            col = mix(col, C[i], smoothstep(-.22, .38, n + (fi == float(N - 1) ? .12 : 0.)));   // wide: soft edges
          }
          // light from the surface's slope
          float e = .02;
          vec3 nrm = normalize(vec3(surf(p - vec2(e, 0.)) - surf(p + vec2(e, 0.)), surf(p - vec2(0., e)) - surf(p + vec2(0., e)), 4.*e));
          float spec = pow(clamp(dot(reflect(-normalize(vec3(-.4, .6, .7)), nrm), vec3(0., 0., 1.)), 0., 1.), 12.);
          float shade = clamp(dot(nrm, normalize(vec3(-.4, .6, .7))), 0., 1.);
          // Light fields only brighten (ink type: contrast only rises); the
          // dark slide only deepens (its cream and lead type: likewise).
          col = dark > .5 ? col * (.72 + .28*shade) : mix(col, vec3(1.), .22*spec);
          gl_FragColor = vec4(col, 1.);
        }`,
    };
    const prog = gl.createProgram();
    for (const [type, code] of [[gl.VERTEX_SHADER, src.v], [gl.FRAGMENT_SHADER, src.f]]) {
      const sh = gl.createShader(type); gl.shaderSource(sh, code); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error('backdrop shader: ' + gl.getShaderInfoLog(sh));
      gl.attachShader(prog, sh);
    }
    gl.linkProgram(prog); gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p'); gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const U = name => gl.getUniformLocation(prog, name);
    // any CSS colour, including var() and color-mix(), as 0..1 rgb
    const probe = document.createElement('i'); document.body.appendChild(probe);
    const rgb = css => { probe.style.color = css; return getComputedStyle(probe).color.match(/[\d.]+/g).slice(0, 3).map(v => v / 255); };
    const mix = (x, y, t) => x.map((v, i) => v + (y[i] - v) * t);
    const hue = name => rgb(`var(--${name})`);
    // The ribbons for each field, bottom layer first, the field itself last
    // and widest so the slide still reads as its colour. Every light-slide
    // hue clears 4.5:1 against --ink (tests/ asserts the palette), so the
    // ink type holds wherever a ribbon passes. The dark slide's ribbons stay
    // at or below ink's luminance, plus one lead-tinted deep ribbon kept
    // dim enough that 22px lead-hue labels still clear 4.5:1 over it.
    const RIBBONS = {
      pink:  ['blush', 'cream', 'sky', 'pink'],
      olive: ['cream', 'amber', 'blush', 'olive'],
      sky:   ['cream', 'blush', 'pink', 'sky'],
      blush: ['cream', 'sky', 'pink', 'blush'],
      amber: ['cream', 'blush', 'pink', 'amber'],
      cream: ['blush', 'sky', 'cream'],
    };
    const title = (document.querySelector('.hook') || {}).textContent || document.title;
    const all = [];
    // The ghost words ("(why)", "(but)", "1/2"…) as frosted glass: the
    // backdrop blurred and brightened inside the letters, a light edge and a
    // soft shadow. CSS cannot clip a blur to glyphs, so they are painted
    // here, into the backdrop, from the DOM element's own font and position
    // (which stays in the page, transparent, for the layout pass and proof).
    const soft = document.createElement('canvas'); soft.width = W; soft.height = H;
    const softCtx = soft.getContext('2d');
    const layer = document.createElement('canvas'); layer.width = 1080; layer.height = 1350;
    const lctx = layer.getContext('2d');
    const glass = s => {
      // A reel backdrop wears the glass for the content slide of its scene.
      const words = (s.content ? s.content() : s.slide).querySelectorAll('.giant.ghost');
      if (!words.length) return;
      softCtx.filter = 'blur(5px) brightness(1.18) saturate(1.1)';   // blurred small: cheap
      softCtx.clearRect(0, 0, W, H); softCtx.drawImage(gl.canvas, 0, CH - H, W, H, 0, 0, W, H);
      softCtx.filter = 'none';
      const S = s.slide.getBoundingClientRect(), k = S.width / s.slide.offsetWidth;
      for (const g of words) {
        const cs = getComputedStyle(g), R = g.getBoundingClientRect(), text = g.textContent;
        const x = (R.left - S.left) / k, top = (R.top - S.top) / k;
        // the word's own scale on screen (the reel's card is 0.9) in host pixels
        const z = R.width / g.offsetWidth / k, px = v => parseFloat(v) * z + 'px';
        const setFont = c => {
          c.font = `${cs.fontWeight} ${px(cs.fontSize)} ${cs.fontFamily}`;
          c.fontStretch = parseFloat(cs.fontStretch) >= 125 ? 'expanded' : 'normal';
          c.letterSpacing = cs.letterSpacing === 'normal' ? '0px' : px(cs.letterSpacing);
          c.textBaseline = 'alphabetic';
        };
        setFont(lctx);
        const m = lctx.measureText(text);
        const asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
        // CSS puts the baseline half the leading below the line box's top
        const y = top + (parseFloat(cs.lineHeight) * z - (asc + desc)) / 2 + asc;
        // the glass: the blurred backdrop, kept only inside the letters
        lctx.clearRect(0, 0, 1080, 1350);
        lctx.globalCompositeOperation = 'source-over';
        lctx.fillStyle = '#000'; lctx.fillText(text, x, y);
        lctx.globalCompositeOperation = 'source-in';
        lctx.drawImage(soft, 0, 0, 1080, 1350);
        lctx.fillStyle = s.dark ? 'rgba(255,255,255,.08)' : 'rgba(255,255,255,.22)';
        lctx.fillRect(0, 0, 1080, 1350);
        lctx.globalCompositeOperation = 'source-over';
        const c = s.ctx;
        c.save();
        c.shadowColor = s.dark ? 'rgba(0,0,0,.45)' : 'rgba(59,44,35,.18)';
        c.shadowBlur = 40; c.shadowOffsetY = 14;
        c.drawImage(layer, 0, 0);
        c.restore();
        // The light edge as a bevel, the letter minus itself shifted: a
        // stroke would also trace the variable font's overlapping contours
        // (a box inside the "t").
        lctx.clearRect(0, 0, 1080, 1350);
        lctx.fillStyle = s.dark ? 'rgba(255,255,255,.35)' : 'rgba(255,255,255,.85)';
        lctx.fillText(text, x, y);
        lctx.globalCompositeOperation = 'destination-out';
        lctx.fillStyle = '#000'; lctx.fillText(text, x + 2.5, y + 2.5);
        lctx.globalCompositeOperation = 'source-over';
        c.drawImage(layer, 0, 0);
      }
    };
    const paint = (s, ms) => {
      gl.uniform3fv(U('C'), s.colors.flat()); gl.uniform1i(U('N'), s.n);
      gl.uniform1f(U('seed'), s.seed); gl.uniform1f(U('dark'), s.dark ? 1 : 0);
      gl.uniform1f(U('a'), 2 * Math.PI * (ms % LOOP) / LOOP);
      gl.viewport(0, 0, W, s.h); gl.uniform2f(U('res'), W, s.h);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      s.ctx.drawImage(gl.canvas, 0, CH - s.h, W, s.h, 0, 0, s.ctx.canvas.width, s.ctx.canvas.height);
      glass(s);
    };
    // ms, and optionally the one slide to repaint (render.py films one at a time)
    // Without `only`, just the slides on screen: in the reel the others are
    // swiped away, and repainting all six cards every frame took minutes.
    // In the reel the slides are stacked, so "on screen" is not enough:
    // walk each stack from the top and stop under the first slide that is
    // opaque and squarely in place. Everything below it is covered.
    const onScreen = el => { const r = el.getBoundingClientRect();
      return r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight; };
    const seen = () => {
      const stacks = new Map(), vis = new Set();
      all.forEach(s => { const p = s.slide.parentElement; if (!stacks.has(p)) stacks.set(p, []); stacks.get(p).push(s); });
      stacks.forEach(list => {
        for (let i = list.length - 1; i >= 0; i--) {
          const el = list[i].slide, op = parseFloat(getComputedStyle(el).opacity);
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
      all.forEach(s => (only === true || (only ? s.slide === only : vis.has(s))) && paint(s, ms));
    };
    window.__backdropLoop = LOOP;
    return slide => {
      const dark = slide.classList.contains('dark');
      const name = Object.keys(RIBBONS).find(k => slide.classList.contains(k));
      const ink = hue('ink'), lead = rgb(getComputedStyle(document.body).getPropertyValue('--lead') || 'var(--pink)');
      const colors = dark ? [ink.map(v => v * .45), mix(ink.map(v => v * .6), lead, .16), ink]
                   : name ? RIBBONS[name].map(hue)
                   : [rgb(getComputedStyle(slide).backgroundColor)];
      while (colors.length < 5) colors.push(colors[colors.length - 1]);   // uniform array is 5 long
      const out = document.createElement('canvas'); out.className = 'bg';
      out.width = slide.offsetWidth; out.height = slide.offsetHeight;   // 1080x1350, or a reel backdrop's 1080x1920
      out.setAttribute('aria-hidden', 'true');
      slide.prepend(out);
      const n = dark ? 3 : name ? RIBBONS[name].length : 1;
      const ctx = out.getContext('2d'); ctx.imageSmoothingQuality = 'high';
      const s = { colors: colors.slice(0, 5), dark, slide, ctx,
                  // the reel's returning cover is slide 1 cloned without its id: same seed, no seam
                  seed: [...(title + (slide.id || (slide.closest('.loop') ? 'slide-1' : '')))].reduce((x, c) => (x * 31 + c.charCodeAt(0)) % 9973, 7) / 997 };
      s.colors.length = 5; s.n = n; s.h = Math.round(W * out.height / out.width);
      if (slide.classList.contains('backdrop')) {
        // backdrop i is scene i: the card's slides, then the returning cover
        const i = [...slide.parentElement.querySelectorAll(':scope > .backdrop')].indexOf(slide);
        s.content = () => document.querySelectorAll('.card > .slide, .card > .loop > .slide')[i] || slide;
      }
      all.push(s); paint(s, 0);
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
