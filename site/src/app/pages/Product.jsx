import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { PRODUCT_FIELDS } from '../copy.js';
import { Act, Crumbs, Empty, Err, Eyebrow, Field, Loading, Prov, Section, toast, useLoad, when } from '../ui.jsx';

export default function Product({ oid, pid }) {
  const q = useLoad(() => Promise.all([api.get(`/api/products/${pid}`), api.get(`/api/orgs/${oid}`)]), [pid]);
  const [f, setF] = useState(null);
  const [name, setName] = useState('');
  const [err, setErr] = useState('');
  const fileRef = useRef(null);
  useEffect(() => { if (q.data) { setF(q.data[0].fields); setName(q.data[0].name); } }, [q.data]);
  if (!q.data || !f) return <Loading err={q.err} />;
  const [p, o] = q.data;
  const labels = p.field_labels || {};
  const dirty = name !== p.name || JSON.stringify(f) !== JSON.stringify(p.fields);
  const save = async status => {
    await api.patch(`/api/products/${pid}`, { name, fields: f, ...(status ? { status } : {}) });
    await q.reload();
    toast(status === 'approved' ? 'Approved: campaigns can use this product now' : 'Saved');
  };
  const src = o.sources.find(s => (labels._sources || []).includes(s.id));
  return (
    <>
      <Crumbs items={[['Organizations', '#/orgs'], [o.name, `#/orgs/${oid}/products`], [p.name]]} />
      <div className="page">
        <div className="row between">
          <div><Eyebrow>Product or service</Eyebrow><h1>{p.name}</h1></div>
          {p.status === 'approved' && <a className="btn" href={`#/campaigns/new?org=${oid}&product=${pid}`}>New campaign for {p.name}</a>}
        </div>
        <div className="row" style={{ marginBottom: 20 }}>
          <span className={`tag ${p.status === 'approved' ? 'good' : p.status === 'draft' ? 'warn' : ''}`}>{p.status === 'draft' ? 'needs approval' : p.status}</span>
          {p.origin === 'research' && <span className="note">Found through research{src ? <> in <a href={src.url || '#'} target="_blank" rel="noreferrer">{src.name}</a></> : ''}{labels._evidence ? <> · “{labels._evidence}”</> : ''}</span>}
        </div>
        <div className="cols">
          <div>
            <div className="card">
              <Field label="Name" value={name} onChange={setName} />
              <div className="fields">
                {Object.entries(PRODUCT_FIELDS).map(([k, [label, ph]]) => (
                  <div key={k}>
                    <Field label={label} value={f[k]} placeholder={ph} area onChange={v => setF(x => ({ ...x, [k]: v }))} />
                    {f[k] && labels[k] && <div style={{ marginTop: 5 }}><Prov label={labels[k]} /></div>}
                  </div>
                ))}
              </div>
              <Err>{err}</Err>
              <div className="actions">
                {p.status === 'draft'
                  ? <Act className="btn" onError={setErr} run={() => save('approved')}>Approve this information</Act>
                  : <Act className="btn" disabled={!dirty} onError={setErr} run={() => save()}>Save changes</Act>}
                {p.status === 'draft' && dirty && <Act className="line" onError={setErr} run={() => save()}>Save without approving</Act>}
              </div>
            </div>

            <Section count={p.sources.length}>Material for this product</Section>
            {p.sources.length ? p.sources.map(s => (
              <div key={s.id} className="item"><span className="k">▤</span>
                <span className="n"><b>{s.name}</b><small>{s.kind} · {when(s.added)}{s.confidential ? ' · confidential' : ''}</small></span>
                <Act className="line tiny danger" run={async () => { await api.del(`/api/sources/${s.id}`); q.reload(); }}>Remove</Act></div>
            )) : <Empty>Nothing attached. Add a product sheet, photos or the store page.</Empty>}
            <div className="row" style={{ marginTop: 12 }}>
              <button className="line" onClick={() => fileRef.current.click()}>Attach files</button>
              <input ref={fileRef} type="file" multiple hidden onChange={async e => {
                for (const file of e.target.files) {
                  try { await api.form(`/api/orgs/${oid}/sources`, { file, product_id: pid }); } catch (x) { setErr(x.message); break; }
                }
                q.reload();
              }} />
            </div>
          </div>
          <aside>
            <div className="card"><h4>Before a campaign uses it</h4><p className="note">Researched details stay labelled until you edit them. Editing a detail makes it yours (<Prov label="provided" />).</p></div>
            <div className="card"><h4>Campaigns <span className="count">{p.campaigns.length}</span></h4>
              {p.campaigns.length ? p.campaigns.map(c => <p key={c.id} className="note" style={{ margin: '6px 0 0' }}><a href={`#/campaigns/${c.id}`}>{c.name}</a></p>) : <p className="note">None yet.</p>}</div>
          </aside>
        </div>
      </div>
    </>
  );
}
