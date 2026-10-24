import { useEffect, useRef } from 'react';

// Colours come from the page theme (dark or light), read once per frame.
let ICE = '145,208,255';
let PAPER = '240,241,237';
const readTheme = () => {
  const cs = getComputedStyle(document.documentElement);
  ICE = cs.getPropertyValue('--ice-rgb').trim() || ICE;
  PAPER = cs.getPropertyValue('--line-rgb').trim() || PAPER;
};
const BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];

/* Runs draw(t) on a canvas at ~30fps while visible and not paused; one static frame under reduced motion. */
function useCanvasLoop(ref, paused, draw) {
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0, last = 0, visible = true, t0 = performance.now();
    const fit = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = width * dpr; canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      readTheme();
      draw(ctx, width, height, 2.2);
    };
    const tick = now => {
      raf = requestAnimationFrame(tick);
      if (now - last < 33 || !visible) return;
      last = now;
      const r = canvas.getBoundingClientRect();
      readTheme();
      draw(ctx, r.width, r.height, (now - t0) / 1000);
    };
    const mo = new MutationObserver(fit);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(canvas);
    const ro = new ResizeObserver(fit);
    ro.observe(canvas);
    fit();
    if (!reduce && !paused) raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); io.disconnect(); ro.disconnect(); mo.disconnect(); };
  }, [ref, paused, draw]);
}

/* ---------- hands ---------- */

const sdCapsule = (px, py, ax, ay, bx, by, r) => {
  const pax = px - ax, pay = py - ay, bax = bx - ax, bay = by - ay;
  const h = Math.max(0, Math.min(1, (pax * bax + pay * bay) / (bax * bax + bay * bay || 1)));
  return Math.hypot(pax - bax * h, pay - bay * h) - r;
};

// Skeleton in palm units: wrist at origin, fingers toward +v. Fingers are thin and spread so they read as fingers.
function hand({ x, y, angle, scale, mirror = 1, curls, robot = false }) {
  const fx = Math.cos(angle), fy = Math.sin(angle), sx = -fy * mirror, sy = fx * mirror;
  const P = (u, v) => [x + (sx * u + fx * v) * scale, y + (sy * u + fy * v) * scale];
  const caps = [], joints = [], tips = [];
  const add = (a, b, r, seg) => caps.push({ a, b, r: r * scale, seg });
  add(P(0, -3.4), P(0, -0.1), robot ? 0.2 : 0.24, 'arm');
  add(P(-0.2, 0.08), P(-0.24, 0.78), 0.2, 'palm');
  add(P(0.2, 0.08), P(0.22, 0.78), 0.2, 'palm');
  add(P(0, 0.05), P(0, 0.8), 0.24, 'palm');
  const fr = robot ? 0.055 : 0.06;
  // [knuckle u, length, splay] index → pinky
  [[-0.32, 1.0, -0.28], [-0.11, 1.12, -0.09], [0.11, 1.05, 0.09], [0.31, 0.84, 0.27]].forEach(([u, len, splay], i) => {
    let [px, py] = [u, 0.9], dir = splay;
    [0.42, 0.27, 0.21].forEach((L, j) => {
      dir += curls[i] * (0.6 + j * 0.4);
      const nx = px + Math.sin(dir) * L * len, ny = py + Math.cos(dir) * L * len;
      add(P(px, py), P(nx, ny), fr - j * 0.008, 'finger');
      joints.push(P(px, py));
      [px, py] = [nx, ny];
    });
    tips.push(P(px, py));
  });
  let [px, py] = [-0.34, 0.28], dir = -0.95 + curls[4];
  [0.36, 0.28].forEach(L => {
    const nx = px + Math.sin(dir) * L, ny = py + Math.cos(dir) * L;
    add(P(px, py), P(nx, ny), fr + 0.012, 'finger');
    joints.push(P(px, py));
    [px, py] = [nx, ny];
    dir += 0.35 + curls[4] * 0.6;
  });
  tips.unshift(P(px, py));
  return { caps, joints, tips, frame: { x, y, fx, fy, scale } };
}

const DIR = ['-', '\\', '|', '/'];
const dirChar = cap => {
  const a = Math.atan2(cap.b[1] - cap.a[1], cap.b[0] - cap.a[0]);
  return DIR[((Math.round(a / (Math.PI / 4)) % 4) + 4) % 4];
};

// Contour-first: a bright outline that follows each segment, a sparse dithered interior, and a forearm that fades out.
function rasterHand(ctx, h, W, H, cw, ch, robot) {
  let x0 = W, y0 = H, x1 = 0, y1 = 0;
  for (const c of h.caps) {
    for (const [px, py] of [c.a, c.b]) {
      x0 = Math.min(x0, px - c.r); x1 = Math.max(x1, px + c.r);
      y0 = Math.min(y0, py - c.r); y1 = Math.max(y1, py + c.r);
    }
  }
  const c0 = Math.max(0, Math.floor(x0 / cw)), c1 = Math.min(Math.ceil(W / cw), Math.ceil(x1 / cw));
  const r0 = Math.max(0, Math.floor(y0 / ch)), r1 = Math.min(Math.ceil(H / ch), Math.ceil(y1 / ch));
  const { x: wx, y: wy, fx, fy, scale } = h.frame;
  const edge = Math.max(cw, ch) * 0.95;
  for (let r = r0; r < r1; r++) {
    for (let c = c0; c < c1; c++) {
      const px = c * cw + cw / 2, py = r * ch + ch / 2;
      let d = Infinity, best = null;
      for (const cap of h.caps) {
        const v = sdCapsule(px, py, cap.a[0], cap.a[1], cap.b[0], cap.b[1], cap.r);
        if (v < d) { d = v; best = cap; }
      }
      if (d > 0) continue;
      const along = ((px - wx) * fx + (py - wy) * fy) / scale;           // < 0 means forearm
      const fade = along >= -0.1 ? 1 : Math.max(0, 1 + (along + 0.1) / 1.1);
      if (fade <= 0.02) continue;
      const onEdge = -d < edge;
      const bay = BAYER[r % 4][c % 4] / 16;
      let chr, a;
      if (robot) {
        const joint = best.seg === 'finger' && h.joints.some(([jx, jy]) => Math.hypot(px - jx, py - jy) < best.r * 0.85);
        if (joint) { chr = 'o'; a = 0.95; }
        else if (onEdge) { chr = dirChar(best); a = 0.9; }
        else if (best.seg === 'palm') { if (bay > 0.45) continue; chr = (r % 2) ? '=' : '+'; a = 0.45; }
        else if (best.seg === 'arm') { if (r % 2) continue; chr = '='; a = 0.4; }
        else { chr = ':'; a = 0.5; }
        ctx.fillStyle = `rgba(${ICE},${a * fade})`;
      } else {
        if (onEdge) { chr = best.seg === 'finger' || best.seg === 'arm' ? dirChar(best) : '*'; a = 0.85; }
        else {
          const shade = Math.min(1, -d / (best.r * 1.2)) * 0.6;
          if (bay > shade + 0.15) continue;
          chr = shade > 0.4 ? '+' : shade > 0.2 ? ':' : '.'; a = 0.4;
        }
        ctx.fillStyle = `rgba(${PAPER},${a * fade})`;
      }
      ctx.fillText(chr, c * cw, r * ch + ch * 0.8);
    }
  }
}

export function Hands({ paused, clearRef }) {
  const ref = useRef(null);
  const draw = useRef((ctx, W, H, t) => {
    ctx.clearRect(0, 0, W, H);
    const small = W < 760;
    const cw = small ? 5 : 6, ch = small ? 9 : 10, s = Math.min(W, H) * (small ? 0.13 : 0.2);
    ctx.font = `${small ? 8 : 10}px "IBM Plex Mono", monospace`;
    // Human leads with small motion; the robot answers late and larger.
    const human = hand({
      x: W * 0.97, y: Math.max(H * 0.1, 96), angle: 2.55 + Math.sin(t * 0.5) * 0.025, scale: s,
      curls: [0, 1, 2, 3, 4].map(i => 0.05 + Math.sin(t * 0.9 + i * 0.7) * 0.04)
    });
    const robot = hand({
      x: -W * 0.01, y: H * 0.62, angle: -0.38 + Math.sin(t * 0.5 - 0.6) * 0.09, scale: s * 0.95, mirror: -1, robot: true,
      curls: [0, 1, 2, 3, 4].map(i => -0.04 - Math.sin(t * 0.9 + i * 0.7 - 0.7) * 0.16)
    });
    rasterHand(ctx, human, W, H, cw, ch, false);
    ctx.shadowColor = `rgba(${ICE},.6)`; ctx.shadowBlur = 6;
    rasterHand(ctx, robot, W, H, cw, ch, true);
    ctx.shadowBlur = 0;
    // Strings: faint, and fainter still where they pass behind the headline.
    const box = clearRef?.current?.getBoundingClientRect();
    const host = ref.current?.getBoundingClientRect();
    const clear = box && host ? [box.left - host.left - 24, box.top - host.top - 24, box.right - host.left + 24, box.bottom - host.top + 24] : null;
    ctx.lineWidth = 0.7;
    human.tips.forEach((a, i) => {
      const b = robot.tips[i];
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2 + 40 + Math.sin(t * 1.1 + i) * 8;
      let prev = a;
      for (let k = 1; k <= 40; k++) {
        const u = k / 40;
        const p = [(1 - u) ** 2 * a[0] + 2 * (1 - u) * u * mx + u * u * b[0], (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * my + u * u * b[1]];
        const inside = clear && p[0] > clear[0] && p[0] < clear[2] && p[1] > clear[1] && p[1] < clear[3];
        ctx.strokeStyle = `rgba(${ICE},${inside ? 0.05 : 0.32})`;
        ctx.beginPath(); ctx.moveTo(prev[0], prev[1]); ctx.lineTo(p[0], p[1]); ctx.stroke();
        prev = p;
      }
    });
  }).current;
  useCanvasLoop(ref, paused, draw);
  return <canvas ref={ref} className="art-fill" aria-hidden="true" />;
}

/* ---------- orb ---------- */

export function Orb({ paused, size = 300 }) {
  const ref = useRef(null);
  const draw = useRef((ctx, W, H, t) => {
    ctx.clearRect(0, 0, W, H);
    const cw = 6, ch = 9, cols = Math.floor(W / cw), rows = Math.floor(H / ch);
    ctx.font = '9px "IBM Plex Mono", monospace';
    ctx.shadowColor = `rgba(${ICE},.7)`; ctx.shadowBlur = 5;
    const lx = Math.cos(t * 0.6), lz = Math.sin(t * 0.6) * 0.6 + 0.5, ly = -0.45, ln = Math.hypot(lx, ly, lz);
    const ramp = ' .·:-=+*#%@';
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const nx = (c - cols / 2 + 0.5) / (cols / 2), ny = (r - rows / 2 + 0.5) / (rows / 2), q = nx * nx + ny * ny;
        if (q > 1) continue;
        const nz = Math.sqrt(1 - q), d = Math.max(0, (nx * lx + ny * ly + nz * lz) / ln);
        const v = d * 0.85 + 0.1 + (BAYER[r % 4][c % 4] / 16 - 0.5) * 0.18;
        const k = Math.max(0, Math.min(ramp.length - 1, Math.floor(v * ramp.length)));
        if (k === 0) continue;
        ctx.fillStyle = `rgba(${ICE},${0.25 + v * 0.75})`;
        ctx.fillText(ramp[k], c * cw, r * ch + 7);
      }
    }
    ctx.shadowBlur = 0;
  }).current;
  useCanvasLoop(ref, paused, draw);
  return <canvas ref={ref} style={{ width: size, height: size }} aria-hidden="true" />;
}

/* ---------- dithered "photograph" ---------- */

export function DitherPhoto({ seed = 1 }) {
  const ref = useRef(null);
  useEffect(() => {
    const paint = () => {
    readTheme();
    const [ir, ig, ib] = ICE.split(',').map(Number);
    const c = ref.current, ctx = c.getContext('2d');
    const W = (c.width = 180), H = (c.height = 130);
    const blobs = [[0.3, 0.55, 0.22], [0.62, 0.5, 0.18], [0.82, 0.62, 0.14], [0.5, 0.95, 0.4]];
    const img = ctx.createImageData(W, H);
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        let v = 0.15 + 0.35 * (y / H) * Math.sin(seed + x / 30) ** 2;
        for (const [bx, by, br] of blobs) v += Math.max(0, 1 - Math.hypot(x / W - bx, (y / H - by) * 0.8) / br) * 0.6;
        const on = v > (BAYER[y % 4][x % 4] + 0.5) / 16;
        const i = (y * W + x) * 4;
        img.data.set(on ? [ir, ig, ib, 220] : [0, 0, 0, 0], i);
      }
    }
    ctx.putImageData(img, 0, 0);
    };
    paint();
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  }, [seed]);
  return <canvas ref={ref} className="dither" aria-hidden="true" />;
}

/* ---------- closing particle grid ---------- */

export function ParticleGrid({ paused }) {
  const ref = useRef(null);
  const draw = useRef((ctx, W, H, t) => {
    ctx.clearRect(0, 0, W, H);
    const gap = 26;
    for (let y = gap / 2; y < H; y += gap) {
      for (let x = gap / 2; x < W; x += gap) {
        const d = Math.hypot(x - W / 2, y - H * 0.55);
        const w = Math.sin(d / 60 - t * 1.2);
        const a = 0.05 + Math.max(0, w) * 0.22 * Math.max(0, 1 - d / (W * 0.6));
        ctx.fillStyle = `rgba(${ICE},${a})`;
        ctx.fillRect(x, y + w * 2, 1.5, 1.5);
      }
    }
  }).current;
  useCanvasLoop(ref, paused, draw);
  return <canvas ref={ref} className="art-fill" aria-hidden="true" />;
}
