import { useEffect, useState } from 'react';

// Hash routes: #/orgs/abc/research?x=1 -> { parts: ['orgs','abc','research'], query: {x:'1'} }
export function parse(hash = location.hash) {
  const [path, qs = ''] = hash.replace(/^#\/?/, '').split('?');
  return { parts: path.split('/').filter(Boolean).map(decodeURIComponent), query: Object.fromEntries(new URLSearchParams(qs)) };
}

export function useRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => { setRoute(parse()); window.scrollTo({ top: 0 }); };
    addEventListener('hashchange', on);
    return () => removeEventListener('hashchange', on);
  }, []);
  return route;
}

export const go = path => { location.hash = path.startsWith('#') ? path : `#${path}`; };
