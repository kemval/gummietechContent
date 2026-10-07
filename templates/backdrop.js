// The moving backdrop: Neat's technique (github.com/FireCMSco/neat), our own
// code. Neat layers colours one over another wherever a horizontally
// stretched noise field crosses a threshold, curls the result with cos() flow
// warps, and lights a waving surface. One fragment shader does the same here,
// in the locked palette. Neat itself watermarks every render without a paid
// key, which the $0 budget rules out (docs/decisions/rendering.md).
//
// Shared by the slides and the reel (slides_layout.js) and by the web archive
// (site_base.html), so the carousel and the page it links to are one look.
//
//   Ribbons.attach(el, {field, dark, lead, seed, width, height}) → a canvas.bg
//     prepended to `el`, painted at time 0. Returns the handle `paint` takes.
//   Ribbons.paint(handle, ms)  repaints it at a moment of the loop.
//   Ribbons.frame(handle)      [canvas, sx, sy, sw, sh]: that picture, for
//                              anything that needs to sample it (glass).
//   Ribbons.LOOP               ms per seamless loop.
//
// `Ribbons` is null without WebGL: callers keep their flat fields.
//
// One WebGL context serves every surface (a Breakdown has more slides than
// Chrome allows live contexts); each picture is copied to a 2D canvas. The
// shader draws W px wide and is scaled up, like Neat's renderScale: headless
// Chrome runs WebGL on the CPU, and at full size a reel took over fifteen
// minutes. The ribbons are smooth enough not to show it. Time enters only as
// the angle of one LOOP (noise sampled around a circle), so every clip loops
// seamlessly and a still is always the same picture.
window.Ribbons = (() => {
  const gl = document.createElement('canvas').getContext('webgl', { preserveDrawingBuffer: true });
  if (!gl) return null;
  const LOOP = 8000, W = 360;
  gl.canvas.width = W; gl.canvas.height = 640;   // grows for taller shapes
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
        vec2 r = ring(.45);   // a small circle: the same loop, a slow drift
        return .55*snoise(vec3(p.x*.45, p.y*.55 + r.x, r.y + seed)) + .2*sin(p.x*1.1 + p.y*.7 + a);
      }
      void main(){
        vec2 uv = gl_FragCoord.xy / res; uv.y = 1. - uv.y;
        vec2 p = vec2((uv.x - .5)*3.2, uv.y*3.6*(res.y/res.x)/1.25);   // ribbon scale follows the width
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
        // dark field only deepens (its cream and lead type: likewise).
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
  const probe = document.createElement('i'); probe.hidden = true; document.body.appendChild(probe);
  const rgb = css => { probe.style.color = css; return getComputedStyle(probe).color.match(/[\d.]+/g).slice(0, 3).map(v => v / 255); };
  const mix = (x, y, t) => x.map((v, i) => v + (y[i] - v) * t);
  const hue = name => rgb(`var(--${name})`);

  // The ribbons for each field, bottom layer first, the field itself last
  // and widest so the surface still reads as its colour. Every light hue
  // clears 4.5:1 against --ink (tests/ asserts the palette), so ink type
  // holds wherever a ribbon passes. The dark field's ribbons stay at or below
  // ink's luminance, plus one lead-tinted deep ribbon kept dim enough that
  // 22px lead-hue labels still clear 4.5:1 over it.
  // A surface that belongs to a post passes its palette (lead, support), and
  // its ribbons are that palette's hues and cream only, the field last.
  // Owner's call, 2026-10-06: the fixed table below put pink and sky on
  // every field, so every post read pink-and-blue whatever its colorway, and
  // no-two-posts-in-a-row (render.vary) was invisible under the ribbons. The
  // table is kept for the one surface with no post behind it, the archive
  // index, which mixes every colour.
  const ribbons = (field, palette) => palette && palette.length
    ? [...new Set([...palette, 'cream'])].filter(h => h !== field).concat(field)
    : RIBBONS[field];
  const RIBBONS = {
    pink:  ['blush', 'cream', 'sky', 'pink'],
    olive: ['cream', 'amber', 'blush', 'olive'],
    sky:   ['cream', 'blush', 'pink', 'sky'],
    blush: ['cream', 'sky', 'pink', 'blush'],
    amber: ['cream', 'blush', 'pink', 'amber'],
    cream: ['blush', 'sky', 'cream'],
  };
  const hash = str => [...str].reduce((x, c) => (x * 31 + c.charCodeAt(0)) % 9973, 7) / 997;

  const paint = (s, ms) => {
    if (s.h > gl.canvas.height) gl.canvas.height = s.h;
    const CH = gl.canvas.height;
    gl.uniform3fv(U('C'), s.colors); gl.uniform1i(U('N'), s.n);
    gl.uniform1f(U('seed'), s.seed); gl.uniform1f(U('dark'), s.dark ? 1 : 0);
    gl.uniform1f(U('a'), 2 * Math.PI * (ms % LOOP) / LOOP);
    gl.viewport(0, 0, W, s.h); gl.uniform2f(U('res'), W, s.h);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    // a pixel and a half in from every edge: scaling up samples bilinearly, and at
    // the edge that pulled in the row beyond the picture as a light line
    s.ctx.drawImage(gl.canvas, 1.5, CH - s.h + 1.5, W - 3, s.h - 3, 0, 0, s.ctx.canvas.width, s.ctx.canvas.height);
    if (s.after) s.after(s);
  };

  const attach = (el, { field, palette, dark = false, lead = 'pink', seed = '', width, height } = {}) => {
    const ink = hue('ink');
    // `lead` is a palette name or any CSS colour (the slides pass var(--lead))
    const leadRGB = /^[a-z]+$/.test(lead) ? hue(lead) : rgb(lead);
    const list = dark ? [ink.map(v => v * .45), mix(ink.map(v => v * .6), leadRGB, .16), ink]
               : ribbons(field, palette) ? ribbons(field, palette).map(hue)
               : [hue(field || 'cream')];
    const n = list.length;
    while (list.length < 5) list.push(list[list.length - 1]);   // the uniform array is 5 long
    const out = document.createElement('canvas'); out.className = 'bg';
    out.width = width || el.offsetWidth; out.height = height || el.offsetHeight;
    out.setAttribute('aria-hidden', 'true');
    el.prepend(out);
    const ctx = out.getContext('2d'); ctx.imageSmoothingQuality = 'high';
    const s = { el, dark, ctx, n, colors: list.flat(), seed: hash(seed),
                h: Math.max(1, Math.round(W * out.height / out.width)) };
    paint(s, 0);
    return s;
  };

  const frame = s => [gl.canvas, 1.5, gl.canvas.height - s.h + 1.5, W - 3, s.h - 3];
  return { LOOP, W, attach, paint, frame };
})();
