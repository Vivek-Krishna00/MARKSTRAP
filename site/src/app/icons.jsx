/* One icon family: 24px grid, 1.5px round stroke, colour from the text. Replaces the Unicode glyphs. */
const P = {
  eye: <><path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.75" /></>,
  mail: <><rect x="3" y="5.5" width="18" height="13" rx="1.5" /><path d="m3.5 7 8.5 6.5L20.5 7" /></>,
  clipboard: <><rect x="5" y="4.5" width="14" height="16" rx="1.5" /><path d="M9 4.5V3.5h6v1M8.5 10.5h7M8.5 14h7M8.5 17.5h4" /></>,
  seat: <><path d="M4 18.5V12a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v6.5M4 15h16M7 10V6.5A1.5 1.5 0 0 1 8.5 5h7A1.5 1.5 0 0 1 17 6.5V10" /></>,
  pin: <><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21Z" /><circle cx="12" cy="10" r="2.25" /></>,
  download: <><path d="M12 3.5v11M7.5 10.5 12 15l4.5-4.5M4 17.5v2h16v-2" /></>,
  cart: <><path d="M3 4h2.5l2.2 10.5h10.6L20.5 7H7" /><circle cx="9.5" cy="19" r="1.25" /><circle cx="17" cy="19" r="1.25" /></>,
  flag: <><path d="M5.5 21V4M5.5 4.5h11l-2 4 2 4h-11" /></>,
  file: <><path d="M6 3.5h8l4 4v13H6z" /><path d="M14 3.5v4h4M9 12.5h6M9 16h6" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7.3l3-3a4 4 0 0 0-5.7-5.6l-1.2 1.2" /><path d="M14 10a4 4 0 0 0-5.7-.3l-3 3a4 4 0 0 0 5.7 5.6l1.2-1.2" /></>,
  note: <><path d="m14.5 5.5 4 4L9 19H5v-4z" /><path d="m13 7 4 4" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5" /></>,
  globe: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.6 3.6 5.5 3.6 8.5s-1.1 5.9-3.6 8.5c-2.5-2.6-3.6-5.5-3.6-8.5S9.5 6.1 12 3.5Z" /></>,
  box: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9" /></>,
  play: <><path d="M7.5 5v14L19 12z" /></>,
  music: <><path d="M9 18V5.5l10-2V16" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="16.5" cy="16" r="2.5" /></>,
  type: <><path d="M5 6.5V4.5h14v2M12 4.5v15M9 19.5h6" /></>,
  check: <><path d="m5 12.5 4.5 4.5L19 7.5" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  back: <><path d="M19 12H5M11 6l-6 6 6 6" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
};

export function Icon({ name, size = 18, className = '', label }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" role={label ? 'img' : undefined}
      aria-label={label} aria-hidden={label ? undefined : 'true'}>{P[name] || P.file}</svg>
  );
}
