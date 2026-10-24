import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { ORG_FIELDS, PROV } from '../copy.js';
import { Act, Crumbs, Empty, Err, Eyebrow, Field, Loading, Prov, STACK, Section, toast, useLoad, when } from '../ui.jsx';

const TABS = [['profile', 'Profile'], ['knowledge', 'Knowledge'], ['research', 'Research'], ['products', 'Products'], ['campaigns', 'Campaigns']];
const KIND = { file: '▤', link: '⌁', note: '✎', crawl: '⌕', wikipedia: 'W' };
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
      <div className="page">
        <div className="row between">
          <div><Eyebrow>Organization</Eyebrow><h1>{o.name}</h1></div>
          <a className="btn" href={`#/campaigns/new?org=${oid}`}>New campaign</a>
        </div>
        <p className="lead">{o.fields.description || 'Add a short description in the profile, or let research suggest one.'}{o.researched_at ? ` · Last researched ${when(o.researched_at)}` : ''}</p>
        <nav className="steps" aria-label="Organization sections">
          {TABS.map(([k, label]) => (
            <a key={k} href={`#/orgs/${oid}/${k}`} className={tab === k ? 'on' : ''} aria-current={tab === k ? 'page' : undefined}>
              {label}{badge[k] > 0 && <span className="count">{badge[k]}</span>}
            </a>
          ))}
        </nav>
        <Tab o={o} reload={q.reload} />
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
  return (
    <div className="cols">
      <div>
        <Section>What you told us</Section>
        <div className="card">
          <p className="note" style={{ marginTop: 0 }}>Everything here is labelled <Prov label="provided" /> and is used as fact in every campaign.</p>
          <Field label="Organization name" value={name} onChange={setName} />
          <div className="fields">
            {Object.entries(ORG_FIELDS).map(([k, [label, ph]]) => (
              <Field key={k} label={label} value={f[k]} placeholder={ph} onChange={v => setF(x => ({ ...x, [k]: v }))}
                area={['description', 'customers', 'competitors', 'notes'].includes(k)} wide={['description', 'notes'].includes(k)} />
            ))}
          </div>
          <Err>{err}</Err>
          <div className="actions">
            <Act className="btn" disabled={!dirty} busy="Saving…" onError={setErr}
              run={async () => { await api.patch(`/api/orgs/${o.id}`, { name, fields: f }); await reload(); toast('Profile saved'); }}>Save changes</Act>
          </div>
        </div>

        <Section count={Object.values(secs).flat().length}>Approved profile</Section>
        {Object.keys(secs).length ? (
          <div className="card">
            {Object.entries(o.sections).filter(([k]) => secs[k]).map(([k, title]) => (
              <div key={k} style={{ padding: '10px 0', borderBottom: '1px solid var(--rule)' }}>
                <div className="kicker">{title}</div>
                {secs[k].map(i => <div key={i.id} className="row" style={{ marginTop: 6 }}><span>{String(i.value)}</span><Prov label={i.label} /></div>)}
              </div>
            ))}
            <p className="note" style={{ marginBottom: 0 }}>Only findings you approved appear here and reach your campaigns.</p>
          </div>
        ) : <Empty>Nothing approved yet. Run research, then review what it found.</Empty>}
        {pending > 0 && <div className="card warn" style={{ marginTop: 14 }}><b>{pending} findings are waiting for your review.</b> <a href={`#/orgs/${o.id}/research`}>Review them</a></div>}
        {missing.length > 0 && <>
          <Section count={missing.length}>Missing information</Section>
          <div className="card"><ul className="clean">{missing.map(m => <li key={m.id}>{String(m.value)} <Prov label="missing" /></li>)}</ul></div>
        </>}
      </div>
      <aside>
        <div className="card"><h4>How labels work</h4>
          {Object.entries(PROV).map(([k, [, help]]) => <p key={k} className="note" style={{ margin: '8px 0 0' }}><Prov label={k} /> {help}</p>)}
        </div>
        <div className="card"><h4>Remove this organization</h4>
          <p className="note">Hides it with its products and campaigns. Your files stay on this machine.</p>
          {sure ? <div className="row"><Act className="line danger tiny" run={async () => { await api.del(`/api/orgs/${o.id}`); go('/orgs'); }}>Yes, remove</Act>
            <button className="line tiny" onClick={() => setSure(false)}>Cancel</button></div>
            : <button className="line tiny danger" onClick={() => setSure(true)}>Remove…</button>}
        </div>
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
    <div className="cols">
      <div>
        <p className="lead">Everything you add here becomes this organization's reusable knowledge. It supports research, every product and every future campaign.</p>
        <div className={`drop${over ? ' over' : ''}`} role="button" tabIndex={0} onClick={() => fileRef.current.click()}
          onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && fileRef.current.click()}
          onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); send([...e.dataTransfer.files]); }}>
          <pre aria-hidden="true">{STACK}</pre>
          <div><div className="big">Drop files, or click to choose</div>
            <div className="note">Brand guidelines, catalogues, case studies, past campaigns, customer research, images, logos, videos</div>
            <div className="tags" style={{ marginTop: 8 }}>{['pdf', 'txt', 'md', 'csv', 'images', 'logos', 'videos'].map(t => <span key={t} className="tag">{t}</span>)}</div></div>
          <input ref={fileRef} type="file" multiple hidden onChange={e => send([...e.target.files])} />
        </div>
        <div className="fields">
          <div><label className="f" htmlFor="k-url">Website or page link</label>
            <div className="row" style={{ flexWrap: 'nowrap' }}><input id="k-url" value={url} placeholder="https://" onChange={e => setUrl(e.target.value)} />
              <Act busy="Reading…" disabled={!url.trim()} run={async () => { if (await add({ url })) setUrl(''); }}>Add</Act></div></div>
          <div><label className="f" htmlFor="k-note">Or in your own words</label>
            <div className="row" style={{ flexWrap: 'nowrap' }}><input id="k-note" value={note} placeholder="What you do, who it's for, what makes it different" onChange={e => setNote(e.target.value)} />
              <Act disabled={!note.trim()} run={async () => { if (await add({ text: note })) setNote(''); }}>Add</Act></div></div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <label className="chk"><input type="checkbox" checked={conf} onChange={e => setConf(e.target.checked)} /> Confidential</label>
          {products.length > 0 && <select style={{ width: 'auto' }} value={prod} onChange={e => setProd(e.target.value)} aria-label="Attach to a product">
            <option value="">For the whole organization</option>{products.map(p => <option key={p.id} value={p.id}>For {p.name}</option>)}</select>}
        </div>
        <Err>{err}</Err>

        <Section count={provided.length}>Your materials</Section>
        {provided.length ? provided.map(s => <SourceRow key={s.id} s={s} o={o} reload={reload} />)
          : <Empty>Nothing yet. Most organizations start with their website and a brand guide.</Empty>}
        {found.length > 0 && <>
          <Section count={found.length}>Read during research</Section>
          {found.map(s => <SourceRow key={s.id} s={s} o={o} reload={reload} />)}
        </>}
      </div>
      <aside>
        <div className="card"><h4>Confidential material</h4><p className="note">Used to understand your business, never quoted in public copy. If a concept repeats its wording, the review flags it before anything goes live.</p></div>
        <div className="card"><h4>Next</h4><p className="note">When you've added what you have, let us research the organization and prepare an editable profile.</p>
          <div className="actions" style={{ marginTop: 12 }}><a className="btn" href={`#/orgs/${o.id}/research`}>Go to research</a></div></div>
      </aside>
    </div>
  );
}

function SourceRow({ s, o, reload }) {
  const product = o.products.find(p => p.id === s.product_id);
  const img = s.path && IMG.test(s.path);
  return (
    <div className="item">
      <span className="k">{img ? <img src={`/api/sources/${s.id}/file`} alt="" /> : KIND[s.kind] || '▤'}</span>
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
    <div className="cols">
      <div>
        <div className={`card${running ? ' ice' : ''}`}>
          <h3>{running ? 'Researching…' : o.researched_at ? 'Research again' : 'Research this organization'}</h3>
          {running ? <>
            <p className="note pulse">{st.step || 'Working'}. You can leave this page; it keeps going.</p>
            <div className="stagebar"><i style={{ width: '60%' }} /></div>
          </> : <>
            <p className="note" style={{ marginTop: 0 }}>With your approval, we will read only:</p>
            <ul className="clean">
              <li>{plan.website ? <>Your website <span className="mono">{plan.website}</span>, up to {plan.max_pages} pages</> : <>No website yet. <a href={`#/orgs/${o.id}/profile`}>Add one in the profile</a></>}</li>
              <li>{plan.competitors.length ? <>Competitor home pages: {plan.competitors.join(', ')}</> : 'No competitor websites listed'}</li>
              <li>The Wikipedia article for “{plan.wikipedia}”, if there is one</li>
              <li>{plan.materials}</li>
            </ul>
            <p className="note">Findings are not used anywhere until you approve them. Re-running replaces earlier public sources and pending findings; what you approved or rejected stays.</p>
            <div className="actions" style={{ marginTop: 14 }}>
              <Act className="btn" busy="Starting…" run={async () => { await api.post(`/api/orgs/${o.id}/research`, { approved: true }); await reload(); }}>Research with my approval</Act>
            </div>
          </>}
          {st.status === 'failed' && <Err>Research stopped: {st.error}</Err>}
          {(st.notes || []).length > 0 && <ul className="clean" style={{ marginTop: 10 }}>{st.notes.map((n, i) => <li key={i} className="note">{n}</li>)}</ul>}
        </div>

        {order.length > 0 && <div className="row between" style={{ marginTop: 26 }}>
          <h3 style={{ margin: 0 }}>Findings to review</h3>
          {solid.length > 0 && <Act className="line tiny" run={async () => { await api.post('/api/findings/bulk', { ids: solid.map(f => f.id), status: 'approved' }); reload(); }}>
            Approve {solid.length} backed by a source</Act>}
        </div>}
        {order.map(k => (
          <div key={k}>
            <Section count={groups[k].length}>{k === 'missing' ? 'Missing information' : o.sections[k]}</Section>
            <div className="card tight">{groups[k].map(f => <FindingRow key={f.id} f={f} o={o} reload={reload} />)}</div>
          </div>
        ))}
        {!order.length && !running && <Empty>No findings yet.</Empty>}
      </div>
      <aside>
        <div className="card"><h4>Never assumptions as facts</h4><p className="note">Each finding carries a label. We set it by checking the quoted evidence against the source, not by trusting the model.</p>
          {Object.keys(PROV).map(k => <div key={k} style={{ marginTop: 6 }}><Prov label={k} /></div>)}</div>
        <div className="card"><h4>Research sources <span className="count">{research.length}</span></h4>
          {research.length ? research.map(s => <p key={s.id} className="note" style={{ margin: '6px 0 0' }}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a></p>)
            : <p className="note">None yet.</p>}
          {o.researched_at && <p className="note">Latest research: {when(o.researched_at)}</p>}</div>
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
    <div className="cols">
      <div>
        <p className="lead">An organization can have many products or services. Campaigns can use a product only after you approve its information.</p>
        {list.length ? list.map(p => (
          <div key={p.id} className="item">
            <span className="k">◇</span>
            <span className="n"><b><a href={`#/orgs/${o.id}/products/${p.id}`}>{p.name}</a></b>
              <small>{p.fields.category || p.fields.description || 'No description'}</small></span>
            <span className="row">
              {p.status === 'draft' && <><Prov label={p.field_labels?.description || 'research'} /><span className="tag warn">needs approval</span>
                <Act className="line tiny" run={async () => { await api.patch(`/api/products/${p.id}`, { status: 'approved' }); reload(); }}>Approve</Act></>}
              {p.status === 'approved' && <span className="tag good">approved</span>}
              {p.status === 'archived' ? <Act className="line tiny" run={async () => { await api.patch(`/api/products/${p.id}`, { status: 'approved' }); reload(); }}>Restore</Act>
                : <Act className="line tiny" run={async () => { await api.patch(`/api/products/${p.id}`, { status: 'archived' }); reload(); }}>Archive</Act>}
            </span>
          </div>
        )) : <Empty>No products yet. Add one below, or run research to find them.</Empty>}
        <label className="chk" style={{ marginTop: 12 }}><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} /> Show archived</label>

        <Section>Add a product or service</Section>
        <div className="card">
          <div className="fields">
            <Field label="Name" value={name} onChange={setName} placeholder="Xbox Game Pass" />
            <Field label="Description" hint="optional" value={desc} onChange={setDesc} placeholder="What it is" />
          </div>
          <Err>{err}</Err>
          <div className="actions">
            <Act className="btn" disabled={!name.trim()} onError={setErr} run={async () => {
              const p = await api.post(`/api/orgs/${o.id}/products`, { name, fields: { description: desc } });
              go(`/orgs/${o.id}/products/${p.id}`);
            }}>Add and fill in details</Act>
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
      <aside><div className="card"><h4>From research</h4><p className="note">Products found during research start as <b>needs approval</b>. Open one to check and edit each detail first.</p></div></aside>
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
            <span className="note">{c.todo || 'Open'} →</span>
          </a>
        )) : <Empty>No campaigns yet.</Empty>}
      </div>
    </div>
  );
}
