import { useCallback, useEffect, useRef, useState } from 'react';
import { PROV } from './copy.js';

/* Load data; reload() refetches. poll(ms) keeps refreshing while `active` is true. */
export function useLoad(fn, deps = [], { poll, active } = {}) {
  const [state, setState] = useState({ data: null, err: null, loading: true });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    try {
      const data = await fnRef.current();
      setState({ data, err: null, loading: false });
      return data;
    } catch (e) {
      setState(s => ({ ...s, err: e.message, loading: false }));
      return null;
    }
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setState(s => ({ ...s, loading: true })); reload(); }, deps);
  const on = typeof active === 'function' ? active(state.data) : active;
  useEffect(() => {
    if (!poll || !on) return undefined;
    const t = setInterval(reload, poll);
    return () => clearInterval(t);
  }, [poll, on, reload]);
  return { ...state, reload, set: data => setState(s => ({ ...s, data })) };
}

/* A button that runs an async action, shows progress and reports errors. */
export function Act({ run, children, busy: busyText, className = 'line', disabled, onError, title, type = 'button' }) {
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);
  return (
    <button type={type} title={title} className={`${className}${busy ? ' pulse' : ''}`} disabled={disabled || busy}
      onClick={async e => {
        setBusy(true);
        try { await run(e); } catch (err) { (onError || toast)(err.message); } finally { if (mounted.current) setBusy(false); }
      }}>
      {busy && busyText ? busyText : children}
    </button>
  );
}

/* Messages that don't block the page (errors from buttons, confirmations). */
export const toast = msg => dispatchEvent(new CustomEvent('ms-toast', { detail: msg }));
export function Toaster() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    const on = e => {
      const id = Math.random();
      setItems(x => [...x, { id, msg: e.detail }]);
      setTimeout(() => setItems(x => x.filter(i => i.id !== id)), 6000);
    };
    addEventListener('ms-toast', on);
    return () => removeEventListener('ms-toast', on);
  }, []);
  return <div className="toasts" role="status" aria-live="polite">{items.map(i => <div key={i.id} className="toast">{i.msg}</div>)}</div>;
}

export function Prov({ label, source }) {
  const [name, help] = PROV[label] || [label, ''];
  return <span className={`prov ${label}`} title={source ? `${help} Source: ${source}` : help}>{name}</span>;
}

export const Sim = ({ children = 'Simulated' }) => <span className="sim" title="Simulated reactions, not real customer behaviour">{children}</span>;

export const fromLabel = f => (/^set for/i.test(f) ? f : `From ${f}`);

export function Field({ label, hint, value, onChange, placeholder, area, rows = 2, type = 'text', from, changed, wide, id, disabled }) {
  const fid = id || `f-${label.replace(/\W+/g, '-').toLowerCase()}`;
  return (
    <div className={wide ? 'wide' : ''}>
      <label className="f" htmlFor={fid}>{label}{hint && <small>{hint}</small>}</label>
      {area
        ? <textarea id={fid} rows={rows} value={value ?? ''} placeholder={placeholder} disabled={disabled} onChange={e => onChange(e.target.value)} />
        : <input id={fid} type={type} value={value ?? ''} placeholder={placeholder} disabled={disabled} onChange={e => onChange(e.target.value)} />}
      {from && <div className={`from${changed ? ' changed' : ''}`}>{changed ? 'Changed for this campaign' : fromLabel(from)}</div>}
    </div>
  );
}

export const Section = ({ children, count }) => <div className="section">{children}{count !== undefined && <span className="count">{count}</span>}</div>;
export const Err = ({ children }) => (children ? <div className="err" role="alert">{children}</div> : null);

export function Empty({ art = EMPTY, children }) {
  return <div className="empty"><pre aria-hidden="true">{art}</pre><div>{children}</div></div>;
}

export function Loading({ err }) {
  if (err) return <div className="page"><Err>{err}</Err></div>;
  return (
    <div className="page" aria-busy="true" aria-label="Loading">
      <div className="skel" style={{ width: '42%', height: 44 }} />
      <div className="skel" style={{ width: '64%', height: 16, marginTop: 18 }} />
      <div className="skel" style={{ width: '100%', height: 180, marginTop: 34 }} />
    </div>
  );
}

export function ThemeToggle() {
  const sys = () => (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  const [t, setT] = useState(() => document.documentElement.dataset.theme || sys());
  useEffect(() => {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('ms-theme', t); } catch { /* storage blocked: still applies for this visit */ }
  }, [t]);
  return <button className="theme" onClick={() => setT(t === 'light' ? 'dark' : 'light')} aria-label="Switch colour theme">{t === 'light' ? '◑ Dark' : '◐ Light'}</button>;
}

export const when = ts => (ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '');
export const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
export const pad = n => String(n).padStart(2, '0');

export const EMPTY = `  _____
 |     |
 | ? ? |
 |_____|`;
export const STACK = ` .---------.
 | ≡≡≡≡≡   |-.
 | ≡≡≡     | |-.
 | ≡≡≡≡    | | |
 '---------' | |
   '---------' |
     '---------'`;

export function Crumbs({ items }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <a href="#/">Home</a>
      {items.filter(Boolean).map(([label, href], i) => (
        <span key={i} className="row" style={{ gap: 6 }}><i>›</i>{href ? <a href={href}>{label}</a> : <span>{label}</span>}</span>
      ))}
    </nav>
  );
}
