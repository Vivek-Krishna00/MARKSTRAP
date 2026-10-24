// Scroll reveals for the site: CSS animations started by IntersectionObserver, no animation library,
// so the site depends on React alone.
// Reduced motion is handled in styles.css (.rv-* animations off, final state shown).
import { useEffect, useRef, useState } from 'react';

function useInView(ref) {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || inView) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setInView(true), { threshold: 0.1 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, inView]);
  return inView;
}

// Word-by-word blur-in. delay = ms between words, stepDuration = seconds per word.
export function BlurText({ text = '', delay = 70, stepDuration = 0.35, distance = 16, blur = 10, className = '' }) {
  const ref = useRef(null);
  const shown = useInView(ref);
  const words = text.split(' ');
  return (
    <p ref={ref} className={`${className} rv-blurtext${shown ? ' in' : ''}`} style={{ display: 'flex', flexWrap: 'wrap' }}
       aria-label={text}>
      {words.map((w, i) => (
        <span key={i} aria-hidden="true" className="rv-word"
              style={{ '--d': `${(i * delay) / 1000}s`, '--t': `${stepDuration * 2}s`, '--y': `${-distance}px`, '--b': `${blur}px` }}>
          {w + (i < words.length - 1 ? ' ' : '')}
        </span>
      ))}
    </p>
  );
}

// Fade + rise (+ optional blur) once when scrolled into view. delay in seconds.
export function AnimatedContent({ children, distance = 28, duration = 0.9, blur = 0, delay = 0, className = '', ease, ...rest }) {
  const ref = useRef(null);
  const shown = useInView(ref);
  return (
    <div ref={ref} className={`${className} rv-rise${shown ? ' in' : ''}`}
         style={{ '--d': `${delay}s`, '--t': `${duration}s`, '--y': `${distance}px`, '--b': `${blur}px` }} {...rest}>
      {children}
    </div>
  );
}

// Counts from 0 to `to` once in view; keeps decimals of `to`.
export function CountUp({ to, suffix = '', duration = 1.6 }) {
  const ref = useRef(null);
  const shown = useInView(ref);
  const still = typeof window !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const places = (String(to).split('.')[1] || '').length;
  const [v, setV] = useState(still ? to : 0);
  useEffect(() => {
    if (!shown || still) return;
    let raf, start;
    const step = now => {
      start ??= now;
      const p = Math.min((now - start) / (duration * 1000), 1);
      setV(to * (1 - Math.pow(1 - p, 3)));  // ease-out cubic
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [shown, still, to, duration]);
  return <span ref={ref}>{v.toFixed(places)}{suffix}</span>;
}
