// Small fetch helpers. Errors carry the server's plain-language message.
async function call(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const d = body.detail;
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map(x => x.msg).join('; ') : r.statusText);
  }
  return r.json();
}
const json = method => (path, body) => call(path, {
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}),
});
export const api = {
  get: path => call(path),
  post: json('POST'),
  put: json('PUT'),
  patch: json('PATCH'),
  del: path => call(path, { method: 'DELETE' }),
  form: (path, fields) => {
    const fd = new FormData();
    Object.entries(fields).forEach(([k, v]) => v !== undefined && v !== null && fd.append(k, v));
    return call(path, { method: 'POST', body: fd });
  },
};
export const C = cid => `/api/campaigns/${encodeURIComponent(cid)}`;
