import { useState } from 'react';
import { Icon } from '../icons.jsx';
import { api } from '../api.js';
import { go } from '../router.js';
import { ORG_FIELDS } from '../copy.js';
import { Act, Crumbs, Empty, Err, Field, Loading, useLoad } from '../ui.jsx';

export function OrgList() {
  const { data, err } = useLoad(() => api.get('/api/orgs'));
  if (!data) return <Loading err={err} />;
  return (
    <>
      <Crumbs items={[['Organizations']]} />
      <div className="page">
        <div className="row between">
          <div><h1>Your <em className="s">clients</em> and brands.</h1></div>
          <a className="btn" href="#/orgs/new"><Icon name="plus" size={16} />New organization</a>
        </div>
        <p className="lead">Each organization keeps its own knowledge, products, campaigns and lessons. Nothing is shared between organizations.</p>
        {data.length ? (
          <div className="org-list">
            {data.map(o => (
              <a key={o.id} className="org-list-row" href={`#/orgs/${o.id}`}>
                <span className="org-list-monogram">{o.name.slice(0, 2).toUpperCase()}</span>
                <span className="org-list-name"><b>{o.name}</b><small>{o.fields.industry || o.fields.description || 'No description yet'}</small></span>
                <span className="org-list-counts">{o.products} {o.products === 1 ? 'product' : 'products'} <i /> {o.campaigns} {o.campaigns === 1 ? 'campaign' : 'campaigns'}</span>
                {o.pending_findings > 0
                  ? <span className="org-review"><b>Profile</b><span>Review</span><Icon name="arrow" size={16} /></span>
                  : <span className="org-open">Open <Icon name="arrow" size={16} /></span>}
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
