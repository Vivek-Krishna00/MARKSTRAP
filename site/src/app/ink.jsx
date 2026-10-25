import { useEffect, useRef, useState } from 'react';

/* Halftone and ASCII artwork from the pitch site, re-inked in the theme accent: paper becomes transparent and the
   ink takes the accent colour, so the same picture works in dark and light mode. Settings per picture match the
   pitch (light = picture on a dark ground; paper/soft = how much of the ground is dropped; tone = photographic). */
const ART = {
  butterfly: { soft: 95, paper: 250, blank: [[593, 48, 764, 147], [696, 740, 860, 826], [0, 924, 191, 963]] },
  flower: { soft: 190, paper: 250 },
  dragonfly: { light: 170, soft: 70 },
  terrain: { paper: 205, soft: 110 },
  jellyfish: { paper: 252, soft: 170 },
  wave: { light: 18, soft: 150 },
  swan: { light: 60, soft: 120 },
  glow: { light: 70, soft: 150 },
  scan: { tone: 1.15 },
};

function useInk() {
  const read = () => getComputedStyle(document.documentElement).getPropertyValue('--ink-rgb').trim() || '145,208,255';
  const [ink, setInk] = useState(read);
  useEffect(() => {
    const update = () => setInk(read());
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const mq = matchMedia('(prefers-color-scheme: light)');
    mq.addEventListener('change', update);
    return () => { mo.disconnect(); mq.removeEventListener('change', update); };
  }, []);
  return ink.split(',').map(Number);
}

export function InkArt({ name, className = '' }) {
  const ref = useRef(null);
  const ink = useInk();
  const key = ink.join(',');
  useEffect(() => {
    const { light = 0, soft = 95, paper = 250, tone = 0, blank = [] } = ART[name] || {};
    const img = new Image();
    let dead = false;
    img.onload = () => {
      const c = ref.current;
      if (dead || !c) return;
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const x = c.getContext('2d', { willReadFrequently: true });
      x.drawImage(img, 0, 0);
      const d = x.getImageData(0, 0, c.width, c.height), px = d.data;
      for (let i = 0; i < px.length; i += 4) {
        const lum = (px[i] + px[i + 1] + px[i + 2]) / 3;
        if (tone) {  // photographic: brightness drives the tint, so the picture keeps its shape
          const t = Math.pow(Math.min(1, (lum / 255) * tone), 0.8);
          px[i] = ink[0]; px[i + 1] = ink[1]; px[i + 2] = ink[2]; px[i + 3] = Math.round(t * 255);
          continue;
        }
        const a = Math.max(0, Math.min(1, light ? (lum - light) / soft : (paper - lum) / soft));
        px[i] = ink[0]; px[i + 1] = ink[1]; px[i + 2] = ink[2]; px[i + 3] = Math.round(a * 255);
      }
      for (const [x0, y0, x1, y1] of blank) {  // captions and watermarks in the source art
        for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) px[(yy * c.width + xx) * 4 + 3] = 0;
      }
      x.putImageData(d, 0, 0);
    };
    img.src = `/art/${name}.jpg`;
    return () => { dead = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, key]);
  return <canvas ref={ref} className={`ink ${className}`} aria-hidden="true" />;
}

/* Which picture frames which part of the app, and on which side. */
export function artFor(parts) {
  const [a, , c, d] = parts;
  if (!a) return ['butterfly', 'right'];
  if (a === 'orgs' && c === 'products') return ['terrain', 'right'];
  if (a === 'orgs' && parts[1] && parts[1] !== 'new') return ['dragonfly', 'right'];
  if (a === 'orgs') return ['flower', 'right'];
  if (a === 'campaigns' && parts[1] === 'new') return ['jellyfish', 'left'];
  const byStep = { brief: ['terrain', 'right'], concepts: ['jellyfish', 'left'], assets: ['wave', 'right'],
    reels: ['glow', 'right'], launch: ['swan', 'right'], results: ['scan', 'left'], next: ['butterfly', 'right'] };
  if (a === 'campaigns') return byStep[c] || (d ? byStep.reels : ['wave', 'right']);
  return ['flower', 'right'];
}

export function BorderArt({ parts }) {
  const [name, side] = artFor(parts);
  return <div className={`border-art ${side} art-${name}`}><InkArt key={name} name={name} /></div>;
}

export function Mark() {
  return <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 26V6h5l8 10L24 6h5v20h-6V15l-7 9-7-9v11Z" /></svg>;
}
