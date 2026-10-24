import { useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { ORG_FIELDS } from '../copy.js';
import { Act, Crumbs, Empty, Err, Eyebrow, Field, Loading, useLoad } from '../ui.jsx';

export function OrgList() {
  const { data, err } = useLoad(() => api.get('/api/orgs'));
  if (!data) return <Loading err={err} />;
  return (
    <>
      <Crumbs items={[['Organizations']]} />
      <div className="page">
        <div className="row between">
          <div><Eyebrow>Organizations</Eyebrow><h1>Your <em className="s">clients</em> and brands.</h1></div>
          <a className="btn" href="#/orgs/new">New organization</a>
        </div>
        <p className="lead">Each organization keeps its own knowledge, products, campaigns and lessons. Nothing is shared between organizations.</p>
        {data.length ? (
          <div className="grid auto">
            {data.map(o => (
              <a key={o.id} className="card tile" href={`#/orgs/${o.id}`}>
                <h3>{o.name}</h3>
                <p className="note" style={{ margin: '0 0 8px' }}>{o.fields.industry || o.fields.description || 'No description yet'}</p>
                <div className="tags"><span className="tag">{o.products} products</span><span className="tag">{o.campaigns} campaigns</span>
                  {o.pending_findings > 0 && <span className="tag warn">{o.pending_findings} to review</span>}</div>
              </a>
            ))}
          </div>
        ) : <Empty>No organizations yet. <a href="#/orgs/new">Create the first one.</a></Empty>}
      </div>
    </>
  );
}

export function OrgNew() {
  const [name, setName] = useState('');
  const [f, setF] = useState({});
  const [err, setErr] = useState('');
  const set = k => v => setF(x => ({ ...x, [k]: v }));
  return (
    <>
      <Crumbs items={[['Organizations', '#/orgs'], ['New']]} />
      <div className="page" style={{ maxWidth: 860 }}>
        <Eyebrow>Step 1 · Organization</Eyebrow>
        <h1>Who are we <em className="s">working for?</em></h1>
        <p className="lead">Only the name is needed now. Skip anything you don't have; you can come back and fill it in, and research can find much of it for you.</p>
        <div className="card">
          <Field label="Organization name" value={name} onChange={setName} placeholder="Microsoft, Midnight Crumb, Sunrise Academy…" id="org-name" />
          <div className="fields">
            {Object.entries(ORG_FIELDS).map(([k, [label, ph]]) => (
              <Field key={k} label={label} hint="optional" value={f[k]} onChange={set(k)} placeholder={ph}
                area={['description', 'customers', 'competitors', 'notes'].includes(k)} wide={['description', 'notes'].includes(k)} />
            ))}
          </div>
          <Err>{err}</Err>
          <div className="actions">
            <Act className="btn" busy="Creating…" disabled={!name.trim()} onError={setErr}
              run={async () => { const o = await api.post('/api/orgs', { name, fields: f }); go(`/orgs/${o.id}/knowledge`); }}>
              Create and add information
            </Act>
            <span className="note">Next: add your website, documents and brand material.</span>
          </div>
        </div>
      </div>
    </>
  );
}
