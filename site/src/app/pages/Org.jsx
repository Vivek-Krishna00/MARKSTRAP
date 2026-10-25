import { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { api } from '../api.js';
import { go } from '../router.js';
import { ORG_FIELDS, PROV } from '../copy.js';
import { Act, Crumbs, Empty, Err, Field, Loading, Prov, STACK, Section, toast, useLoad, when } from '../ui.jsx';

const TABS = [['profile', 'Profile'], ['knowledge', 'Knowledge'], ['research', 'Research'], ['products', 'Products'], ['campaigns', 'Campaigns']];
const KIND = { file: 'file', link: 'link', note: 'note', crawl: 'search', wikipedia: 'globe' };
const IMG = /\.(png|jpe?g|webp|gif|svg)$/i;

export default function Org({ oid, tab }) {
  const q = useLoad(() => api.get(`/api/orgs/${oid}`), [oid], { poll: 2000, active: d => d?.research?.status === 'running' });
  const o = q.data;
  if (!o) return <Loading err={q.err} />;
  const pending = o.findings.filter(f => f.status === 'pending' && f.section !== 'missing').length;
  const drafts = o.products.filter(p => p.status === 'draft').length;
  const badge = { research: pending, products: drafts };
  const Tab = { profile: Profile, knowledge: Knowledge, research: Research, products: Products, campaigns: Campaigns }[tab] || Profile;
  return (
    <>
      <Crumbs items={[['Organizations', '#/orgs'], [o.name]]} />
      <div className="page org-shell">
        <header className="org-head">
          <div className="org-id" aria-hidden="true">{o.name.slice(0, 2).toUpperCase()}</div>
          <div className="org-title">
            <span className="org-kicker">Organization workspace</span>
            <h1>{o.name}</h1>
            <p>{o.fields.description || 'Add a short description in the profile, or let research suggest one.'}</p>
          </div>
          <div className="org-actions">
            {o.researched_at && <span className="org-updated">Research updated<br />{when(o.researched_at)}</span>}
            <a className="btn" href={`#/campaigns/new?org=${oid}`}>New campaign <span aria-hidden="true">↗</span></a>
          </div>
        </header>
        <nav className="steps org-tabs" aria-label="Organization sections">
          {TABS.map(([k, label]) => (
            <a key={k} href={`#/orgs/${oid}/${k}`} className={tab === k ? 'on' : ''} aria-current={tab === k ? 'page' : undefined}>
              {label}{badge[k] > 0 && <span className="count">{badge[k]}</span>}
            </a>
          ))}
        </nav>
        <div className="org-tabbody"><Tab o={o} reload={q.reload} /></div>
      </div>
    </>
  );
}

/* ---------- profile ---------- */

function Profile({ o, reload }) {
  const [f, setF] = useState(o.fields);
  const [name, setName] = useState(o.name);
  const [err, setErr] = useState('');
  const [sure, setSure] = useState(false);
  const dirty = name !== o.name || JSON.stringify(f) !== JSON.stringify(o.fields);
  const secs = o.profile.sections;
  const missing = o.findings.filter(x => x.section === 'missing' && x.status !== 'rejected');
  const pending = o.findings.filter(x => x.status === 'pending' && x.section !== 'missing').length;
  const change = key => value => setF(x => ({ ...x, [key]: value }));
  return (
    <div className="profile-layout">
      <div className="profile-main">
        <div className="profile-intro">
          <div><span className="overline">Profile source</span><h2>Your facts,<br /><em>kept separate.</em></h2></div>
          <p>What you enter here is treated as first-party truth and reused across this organization’s campaigns. Research findings stay separate until you approve them.</p>
        </div>

        <div className="profile-form">
          <section className="profile-group">
            <header><span>01</span><div><h3>Identity</h3><p>The basics every campaign should inherit.</p></div></header>
            <div className="profile-fields">
              <Field label="Organization name" value={name} onChange={setName} />
              <Field label={ORG_FIELDS.website[0]} value={f.website} placeholder={ORG_FIELDS.website[1]} onChange={change('website')} />
              <Field label={ORG_FIELDS.description[0]} value={f.description} placeholder={ORG_FIELDS.description[1]} onChange={change('description')} area rows={3} wide />
            </div>
          </section>

          <section className="profile-group">
            <header><span>02</span><div><h3>Market</h3><p>Where the organization operates and who it serves.</p></div></header>
            <div className="profile-fields">
              <Field label={ORG_FIELDS.industry[0]} value={f.industry} placeholder={ORG_FIELDS.industry[1]} onChange={change('industry')} />
              <Field label={ORG_FIELDS.market[0]} value={f.market} placeholder={ORG_FIELDS.market[1]} onChange={change('market')} />
              <Field label={ORG_FIELDS.customers[0]} value={f.customers} placeholder={ORG_FIELDS.customers[1]} onChange={change('customers')} area rows={3} wide />
            </div>
          </section>

          <section className="profile-group">
            <header><span>03</span><div><h3>Brand</h3><p>The cues that should survive from one campaign to the next.</p></div></header>
            <div className="profile-fields">
              <Field label={ORG_FIELDS.voice[0]} value={f.voice} placeholder={ORG_FIELDS.voice[1]} onChange={change('voice')} />
              <Field label={ORG_FIELDS.colours[0]} value={f.colours} placeholder={ORG_FIELDS.colours[1]} onChange={change('colours')} />
            </div>
          </section>

          <section className="profile-group">
            <header><span>04</span><div><h3>Context</h3><p>Useful boundaries and background for research and strategy.</p></div></header>
            <div className="profile-fields">
              <Field label={ORG_FIELDS.competitors[0]} value={f.competitors} placeholder={ORG_FIELDS.competitors[1]} onChange={change('competitors')} area rows={3} />
              <Field label={ORG_FIELDS.notes[0]} value={f.notes} placeholder={ORG_FIELDS.notes[1]} onChange={change('notes')} area rows={3} />
            </div>
          </section>
        </div>

        <Err>{err}</Err>
        <div className={`profile-save${dirty ? ' dirty' : ''}`}>
          <span>{dirty ? 'Unsaved changes' : 'Everything is up to date'}</span>
          <Act className="btn" disabled={!dirty} busy="Saving…" onError={setErr}
            run={async () => { await api.patch(`/api/orgs/${o.id}`, { name, fields: f }); await reload(); toast('Profile saved'); }}>Save profile <span aria-hidden="true">→</span></Act>
        </div>

        <Section count={Object.values(secs).flat().length}>Approved research</Section>
        {Object.keys(secs).length ? (
          <div className="approved-profile">
            {Object.entries(o.sections).filter(([k]) => secs[k]).map(([k, title]) => (
              <div key={k} className="approved-section">
                <div className="kicker">{title}</div>
                {secs[k].map(i => <div key={i.id} className="row" style={{ marginTop: 6 }}><span>{String(i.value)}</span><Prov label={i.label} /></div>)}
              </div>
            ))}
            <p className="note" style={{ marginBottom: 0 }}>Only findings you approved appear here and reach your campaigns.</p>
          </div>
        ) : <Empty>Nothing approved yet. Run research, then review what it found.</Empty>}
        {pending > 0 && <div className="review-callout"><span>{String(pending).padStart(2, '0')}</span><b>Findings are waiting for your review.</b><a href={`#/orgs/${o.id}/research`}>Review them →</a></div>}
        {missing.length > 0 && <section className="profile-gaps">
          <Section count={missing.length}>Missing information</Section>
          <div className="gap-list">{missing.map((m, i) => <div className="gap-row" key={m.id}>
            <span>{String(i + 1).padStart(2, '0')}</span><b>{String(m.value)}</b><Prov label="missing" />
          </div>)}</div>
        </section>}
      </div>
      <aside className="profile-aside">
        <div className="profile-aside-head"><span className="overline">Evidence key</span><h3>Know where every claim came from.</h3></div>
        <div className="label-legend">
          {Object.entries(PROV).map(([k, [, help]]) => <div key={k}><Prov label={k} /><p>{help}</p></div>)}
        </div>
        <p className="legend-note">Only provided facts and research you approve reach a campaign brief.</p>
        <details className="danger-zone">
          <summary>Organization settings</summary>
          <div><h4>Remove this organization</h4><p>Hides it with its products and campaigns. Your files stay on this machine.</p>
            {sure ? <div className="row"><Act className="line danger tiny" run={async () => { await api.del(`/api/orgs/${o.id}`); go('/orgs'); }}>Yes, remove</Act>
              <button className="line tiny" onClick={() => setSure(false)}>Cancel</button></div>
              : <button className="line tiny danger" onClick={() => setSure(true)}>Remove…</button>}
          </div>
        </details>
      </aside>
    </div>
  );
}

/* ---------- knowledge base ---------- */

function Knowledge({ o, reload }) {
  const [url, setUrl] = useState('');
  const [note, setNote] = useState('');
  const [conf, setConf] = useState(false);
  const [prod, setProd] = useState('');
  const [err, setErr] = useState('');
  const [over, setOver] = useState(false);
  const fileRef = useRef(null);
  const provided = o.sources.filter(s => s.origin === 'provided');
  const found = o.sources.filter(s => s.origin === 'research');
  const products = o.products.filter(p => p.status === 'approved' || p.status === 'draft');
  const add = async fields => {
    setErr('');
    try { await api.form(`/api/orgs/${o.id}/sources`, { ...fields, confidential: conf, product_id: prod }); await reload(); return true; }
    catch (e) { setErr(e.message); return false; }
  };
  const send = async files => { for (const file of files) if (!(await add({ file }))) return; toast(`${files.length} file${files.length > 1 ? 's' : ''} added`); };
  return (
    <div className="knowledge-layout">
      <div className="knowledge-main">
        <div className="knowledge-intro">
          <div><span className="overline">Knowledge base</span><h2>Give the work<br /><em>something real.</em></h2></div>
          <p>Everything you add becomes reusable context for research, products and future campaigns.</p>
        </div>

        <section className="knowledge-ingest">
          <div className={`knowledge-drop${over ? ' over' : ''}`} role="button" tabIndex={0} onClick={() => fileRef.current.click()}
          onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && fileRef.current.click()}
          onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); send([...e.dataTransfer.files]); }}>
            <span className="knowledge-drop-index">01</span>
            <pre aria-hidden="true">{STACK}</pre>
            <div className="knowledge-drop-copy"><h3>Drop files, or click to choose</h3>
              <p>Brand guidelines, catalogues, case studies, past campaigns, customer research, images, logos or videos.</p>
              <span className="knowledge-formats">PDF · TXT · MD · CSV · IMAGES · LOGOS · VIDEOS</span></div>
            <span className="knowledge-drop-action" aria-hidden="true">Choose files ↗</span>
            <input ref={fileRef} type="file" multiple hidden onChange={e => send([...e.target.files])} />
          </div>

          <div className="knowledge-adders">
            <div className="knowledge-adder"><span className="knowledge-add-index">02</span><div><label className="f" htmlFor="k-url">Website or page link</label>
              <div className="knowledge-field"><input id="k-url" value={url} placeholder="https://" onChange={e => setUrl(e.target.value)} />
                <Act className="line" busy="Reading…" disabled={!url.trim()} run={async () => { if (await add({ url })) setUrl(''); }}>Add link</Act></div></div></div>
            <div className="knowledge-adder"><span className="knowledge-add-index">03</span><div><label className="f" htmlFor="k-note">In your own words</label>
              <div className="knowledge-field"><input id="k-note" value={note} placeholder="What you do, who it's for, what makes it different" onChange={e => setNote(e.target.value)} />
                <Act className="line" disabled={!note.trim()} run={async () => { if (await add({ text: note })) setNote(''); }}>Add note</Act></div></div></div>
          </div>

          <div className="knowledge-options">
            <label><input type="checkbox" checked={conf} onChange={e => setConf(e.target.checked)} /><span><b>Confidential</b><small>Use as context, never quote publicly</small></span></label>
            {products.length > 0 && <label><span><b>Attach to</b><small>Choose where this context belongs</small></span><select value={prod} onChange={e => setProd(e.target.value)} aria-label="Attach to a product">
              <option value="">Whole organization</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
          </div>
          <Err>{err}</Err>
        </section>

        <section className="knowledge-library">
          <Section count={provided.length}>Your materials</Section>
          {provided.length ? provided.map(s => <SourceRow key={s.id} s={s} o={o} reload={reload} />)
            : <Empty>Nothing yet. Most organizations start with their website and a brand guide.</Empty>}
          {found.length > 0 && <>
            <Section count={found.length}>Read during research</Section>
            {found.map(s => <SourceRow key={s.id} s={s} o={o} reload={reload} />)}
          </>}
        </section>
      </div>
      <aside className="knowledge-aside">
        <section><span className="overline">Private by design</span><h3>Confidential stays confidential.</h3><p>It can help the system understand your business, but it will never be quoted in public copy. Repeated wording is flagged before anything goes live.</p></section>
        <section className="knowledge-next"><span className="overline">Next step</span><strong>Research</strong><p>When you have added what you know, look for the facts you do not.</p>
          <a href={`#/orgs/${o.id}/research`}>Continue to research <span>→</span></a></section>
      </aside>
    </div>
  );
}

function SourceRow({ s, o, reload }) {
  const product = o.products.find(p => p.id === s.product_id);
  const img = s.path && IMG.test(s.path);
  return (
    <div className="item">
      <span className="k">{img ? <img src={`/api/sources/${s.id}/file`} alt="" /> : <Icon name={KIND[s.kind] || 'file'} />}</span>
      <span className="n"><b>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</b>
        <small>{s.origin === 'research' ? 'public source' : s.kind} · {when(s.added)}{product ? ` · ${product.name}` : ''}{s.chars ? ` · ${s.chars.toLocaleString()} characters read` : ''}</small></span>
      <span className="row">
        {s.origin === 'provided' && <label className="chk"><input type="checkbox" checked={!!s.confidential}
          onChange={async e => { await api.patch(`/api/sources/${s.id}`, { confidential: e.target.checked }); reload(); }} /> Confidential</label>}
        <Act className="line tiny danger" run={async () => { await api.del(`/api/sources/${s.id}`); reload(); }}>Remove</Act>
      </span>
    </div>
  );
}

/* ---------- research ---------- */

function Research({ o, reload }) {
  const st = o.research || {};
  const plan = o.research_plan;
  const running = st.status === 'running';
  const prev = useRef(st.status);
  useEffect(() => { if (prev.current === 'running' && st.status === 'done') toast('Research finished. Review the findings below.'); prev.current = st.status; }, [st.status]);
  const groups = {};
  o.findings.forEach(f => { (groups[f.section] = groups[f.section] || []).push(f); });
  const order = [...Object.keys(o.sections), 'missing'].filter(k => groups[k]);
  const solid = o.findings.filter(f => f.status === 'pending' && ['provided', 'research'].includes(f.label));
  const research = o.sources.filter(s => s.origin === 'research');
  return (
    <div className="research-layout">
      <div className="research-main">
        <section className={`research-plan${running ? ' running' : ''}`}>
          <div className="research-plan-head">
            <div>
              <span className="overline">Research scope</span>
              <h2>{running ? 'Researching…' : o.researched_at ? <>Research<br /><em>again.</em></> : <>Research this<br /><em>organization.</em></>}</h2>
            </div>
            <p>Choose exactly what MarkStrap may read. Nothing enters a campaign until you approve it.</p>
          </div>
          {running ? <div className="research-running">
            <p className="pulse">{st.step || 'Working'}. You can leave this page; it keeps going.</p>
            <div className="stagebar"><i style={{ width: '60%' }} /></div>
          </div> : <>
            <ol className="research-scope">
              <li><span>01</span><div><b>Organization website</b><p>{plan.website ? <><span className="mono">{plan.website}</span> · up to {plan.max_pages} pages</> : <>No website yet. <a href={`#/orgs/${o.id}/profile`}>Add one in the profile</a>.</>}</p></div></li>
              <li><span>02</span><div><b>Competitor pages</b><p>{plan.competitors.length ? plan.competitors.join(', ') : 'No competitor websites listed.'}</p></div></li>
              <li><span>03</span><div><b>Public reference</b><p>The Wikipedia article for “{plan.wikipedia}”, if there is one.</p></div></li>
              <li><span>04</span><div><b>Knowledge base</b><p>{plan.materials}</p></div></li>
            </ol>
            <div className="research-consent">
              <p>Re-running replaces earlier public sources and pending findings. Approved and rejected decisions stay.</p>
              <Act className="btn" busy="Starting…" run={async () => { await api.post(`/api/orgs/${o.id}/research`, { approved: true }); await reload(); }}>Research with my approval <span aria-hidden="true">→</span></Act>
            </div>
          </>}
          {st.status === 'failed' && <Err>Research stopped: {st.error}</Err>}
          {(st.notes || []).length > 0 && <ul className="clean research-notes">{st.notes.map((n, i) => <li key={i} className="note">{n}</li>)}</ul>}
        </section>

        {order.length > 0 && <div className="findings-head">
          <div><span className="overline">Approval queue</span><h3>Findings to review</h3></div>
          {solid.length > 0 && <Act className="line tiny" run={async () => { await api.post('/api/findings/bulk', { ids: solid.map(f => f.id), status: 'approved' }); reload(); }}>
            Approve {solid.length} backed by a source</Act>}
        </div>}
        {order.map(k => (
          <section className="finding-group" key={k}>
            <Section count={groups[k].length}>{k === 'missing' ? 'Missing information' : o.sections[k]}</Section>
            <div className="finding-list">{groups[k].map(f => <FindingRow key={f.id} f={f} o={o} reload={reload} />)}</div>
          </section>
        ))}
        {!order.length && !running && <Empty>No findings yet.</Empty>}
      </div>
      <aside className="research-aside">
        <section className="research-key">
          <span className="overline">Evidence key</span>
          <h3>Evidence before confidence.</h3>
          <p>Labels describe where a claim came from—not how convincing it sounds.</p>
          <div className="research-labels">
            {Object.entries(PROV).map(([k, value]) => <div key={k}><Prov label={k} /><small>{value[1]}</small></div>)}
          </div>
        </section>
        <section className="research-sources">
          <div className="research-sources-head"><span className="overline">Research sources</span><strong>{research.length}</strong></div>
          <div className="research-source-list">
            {research.length ? research.map((s, i) => <a key={s.id} href={s.url} target="_blank" rel="noreferrer"><span>{String(i + 1).padStart(2, '0')}</span><b>{s.name}</b><i aria-hidden="true">↗</i></a>)
              : <p>None yet.</p>}
          </div>
          {o.researched_at && <p className="research-updated">Latest research<br />{when(o.researched_at)}</p>}
        </section>
      </aside>
    </div>
  );
}

function FindingRow({ f, o, reload }) {
  const [edit, setEdit] = useState(false);
  const [val, setVal] = useState(String(f.value));
  const src = o.sources.find(s => f.source_ids.includes(s.id));
  const set = async body => { await api.patch(`/api/findings/${f.id}`, body); setEdit(false); reload(); };
  const missing = f.section === 'missing';
  return (
    <div className={`finding ${f.status}`}>
      <div>
        {edit ? <textarea rows={2} value={val} onChange={e => setVal(e.target.value)} aria-label="Edit finding" />
          : <div className="v">{String(f.value)}</div>}
        <div className="meta">
          <Prov label={f.label} source={src?.name} />
          {f.status !== 'pending' && <span className={`tag ${f.status === 'approved' ? 'good' : ''}`}>{f.status}</span>}
          {f.edited ? <span className="tag">edited by you</span> : null}
          {src && <span className="note">from {src.url ? <a href={src.url} target="_blank" rel="noreferrer">{src.name}</a> : src.name}</span>}
        </div>
        {f.evidence && !edit && <div className="ev">“{f.evidence}”</div>}
      </div>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        {edit ? <>
          <Act className="btn tiny" run={() => set({ value: val, status: 'approved' })}>Save & approve</Act>
          <button className="line tiny" onClick={() => setEdit(false)}>Cancel</button>
        </> : missing ? (
          f.status === 'rejected' ? <Act className="line tiny" run={() => set({ status: 'pending' })}>Undo</Act>
            : <Act className="line tiny" run={() => set({ status: 'rejected' })} title="Hide this gap">Dismiss</Act>
        ) : <>
          {f.status !== 'approved' && <Act className="line tiny" run={() => set({ status: 'approved' })}>Approve</Act>}
          <button className="line tiny" onClick={() => setEdit(true)}>Edit</button>
          {f.status !== 'rejected' ? <Act className="line tiny danger" run={() => set({ status: 'rejected' })}>Reject</Act>
            : <Act className="line tiny" run={() => set({ status: 'pending' })}>Undo</Act>}
        </>}
      </div>
    </div>
  );
}

/* ---------- products ---------- */

function Products({ o, reload }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [merge, setMerge] = useState({ keep: '', drop: '' });
  const [showArchived, setShowArchived] = useState(false);
  const [err, setErr] = useState('');
  const list = o.products.filter(p => p.status !== 'merged' && (showArchived || p.status !== 'archived'));
  const live = o.products.filter(p => ['approved', 'draft'].includes(p.status));
  return (
    <div className="product-layout">
      <div className="product-main">
        <div className="product-intro">
          <div><span className="overline">Product library</span><h2>What {o.name}<br /><em>takes to market.</em></h2></div>
          <p>Keep each product’s facts, proof and restrictions in one place. Only approved information can enter a campaign.</p>
        </div>

        <div className="product-list-head">
          <span>{list.length} {list.length === 1 ? 'product' : 'products'}</span>
          <label className="archive-toggle"><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} /> Include archived</label>
        </div>
        <div className="product-list">
          {list.length ? list.map((p, i) => (
            <div key={p.id} className="product-row">
              <span className="product-index">{String(i + 1).padStart(2, '0')}</span>
              <span className="product-symbol"><Icon name="box" size={20} /></span>
              <span className="product-name"><b><a href={`#/orgs/${o.id}/products/${p.id}`}>{p.name}</a></b>
                <small>{p.fields.category || p.fields.description || 'Description not added yet'}</small></span>
              <span className="product-state">
                {p.status === 'draft' && <><Prov label={p.field_labels?.description || 'research'} /><span className="tag warn">needs approval</span>
                  <Act className="line tiny" run={async () => { await api.patch(`/api/products/${p.id}`, { status: 'approved' }); reload(); }}>Approve</Act></>}
                {p.status === 'approved' && <span className="tag good">approved</span>}
                {p.status === 'archived' ? <Act className="line tiny" run={async () => { await api.patch(`/api/products/${p.id}`, { status: 'approved' }); reload(); }}>Restore</Act>
                  : <Act className="line tiny" run={async () => { await api.patch(`/api/products/${p.id}`, { status: 'archived' }); reload(); }}>Archive</Act>}
              </span>
            </div>
          )) : <Empty>No products yet. Add one below, or run research to find them.</Empty>}
        </div>

        <div className="create-product">
          <div className="create-copy"><span className="overline">Add something new</span><h3>New product or service</h3><p>Start with a name. Add evidence, customers, benefits and campaign rules on the next screen.</p></div>
          <div className="create-fields">
            <div className="fields">
              <Field label="Name" value={name} onChange={setName} placeholder="Xbox Game Pass" />
              <Field label="Description" hint="optional" value={desc} onChange={setDesc} placeholder="What it is" />
            </div>
            <Err>{err}</Err>
            <div className="actions">
              <Act className="btn" disabled={!name.trim()} onError={setErr} run={async () => {
                const p = await api.post(`/api/orgs/${o.id}/products`, { name, fields: { description: desc } });
                go(`/orgs/${o.id}/products/${p.id}`);
              }}>Add and fill in details <span aria-hidden="true">→</span></Act>
            </div>
          </div>
        </div>

        {live.length > 1 && <>
          <Section>Combine duplicates</Section>
          <div className="card">
            <div className="fields">
              <div><label className="f" htmlFor="m-keep">Keep</label><select id="m-keep" value={merge.keep} onChange={e => setMerge(m => ({ ...m, keep: e.target.value }))}>
                <option value="">Choose…</option>{live.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
              <div><label className="f" htmlFor="m-drop">Merge into it</label><select id="m-drop" value={merge.drop} onChange={e => setMerge(m => ({ ...m, drop: e.target.value }))}>
                <option value="">Choose…</option>{live.filter(p => p.id !== merge.keep).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
            </div>
            <p className="note">Empty details are filled from the duplicate; its materials and campaigns move over.</p>
            <Act className="line" disabled={!merge.keep || !merge.drop} run={async () => {
              await api.post(`/api/products/${merge.keep}/merge`, { other: merge.drop }); setMerge({ keep: '', drop: '' }); reload(); toast('Products combined');
            }}>Combine</Act>
          </div>
        </>}
      </div>
      <aside className="product-aside">
        <span className="aside-number">{String(o.products.filter(p => p.status === 'draft').length).padStart(2, '0')}</span>
        <h3>Research suggestions</h3>
        <p>Products found during research stay outside campaigns until you open them, check the details and approve them.</p>
        <a href={`#/orgs/${o.id}/research`}>Review research <span>→</span></a>
      </aside>
    </div>
  );
}

/* ---------- campaigns ---------- */

function Campaigns({ o }) {
  return (
    <div>
      <div className="row between"><p className="lead" style={{ margin: 0 }}>Every campaign belongs to this organization and can focus on one product.</p>
        <a className="btn" href={`#/campaigns/new?org=${o.id}`}>New campaign</a></div>
      <div style={{ marginTop: 20 }}>
        {o.campaigns.length ? o.campaigns.map(c => (
          <a key={c.id} className="todo" href={`#/campaigns/${c.id}/${c.where}`}>
            <span className="tag ice">{c.stage}</span>
            <span><b>{c.name}</b><small>{o.products.find(p => p.id === c.product_id)?.name || 'Whole organization'} · updated {when(c.updated)}</small></span>
            <span className="go">{c.todo || 'Open'} <Icon name="arrow" size={14} /></span>
          </a>
        )) : <Empty>No campaigns yet.</Empty>}
      </div>
    </div>
  );
}
