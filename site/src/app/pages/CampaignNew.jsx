import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { CAMPAIGN_FIELDS, OBJECTIVES } from '../copy.js';
import { Act, Crumbs, Err, Eyebrow, Field, Loading, Section, useLoad } from '../ui.jsx';

const AREA = ['audience', 'required_messages', 'brand_rules', 'prohibited_claims', 'instructions', 'success_metric', 'required_assets'];
const GROUPS = [
  ['Who and where', ['goal', 'audience', 'market', 'language']],
  ['What we offer', ['offer', 'destination', 'required_messages', 'success_metric']],
  ['Where it runs', ['platforms', 'format', 'required_assets', 'start', 'end', 'budget']],
  ['Rules', ['tone', 'brand_rules', 'prohibited_claims', 'instructions']],
];

export function CampaignForm({ fields, setFields, pre = {}, objective, setObjective }) {
  const set = k => v => setFields(x => ({ ...x, [k]: v }));
  return (
    <>
      <Section>Objective</Section>
      <p className="note" style={{ marginTop: -6 }}>It decides how success is measured and stays fixed, so every result is comparable.</p>
      <div className="objs" role="radiogroup" aria-label="Objective">
        {Object.entries(OBJECTIVES).map(([k, [g, help]]) => (
          <button key={k} type="button" role="radio" aria-checked={objective === k} className={`obj${objective === k ? ' on' : ''}`} onClick={() => setObjective(k)}>
            <span className="g">{g}</span><b>{k[0].toUpperCase() + k.slice(1)}</b><span>{help}</span>
          </button>
        ))}
      </div>
      {GROUPS.map(([title, keys]) => (
        <div key={title}>
          <Section>{title}</Section>
          <div className="fields">
            {keys.map(k => {
              const [label, ph] = CAMPAIGN_FIELDS[k];
              return <Field key={k} label={label} placeholder={ph} value={fields[k]} onChange={set(k)} area={AREA.includes(k)}
                type={k === 'start' || k === 'end' ? 'date' : 'text'} from={pre[k]?.from}
                changed={pre[k] && (fields[k] ?? '') !== pre[k].value} />;
            })}
          </div>
        </div>
      ))}
    </>
  );
}

export default function CampaignNew({ org, product }) {
  const orgs = useLoad(() => api.get('/api/orgs'));
  const [oid, setOid] = useState(org || '');
  const [pid, setPid] = useState(product || '');
  const detail = useLoad(() => (oid ? api.get(`/api/orgs/${oid}`) : Promise.resolve(null)), [oid]);
  const [pre, setPre] = useState({});
  const [fields, setFields] = useState({});
  const [objective, setObjective] = useState('');
  const [name, setName] = useState('');
  const [err, setErr] = useState('');
  useEffect(() => {
    if (!oid) return;
    api.get(`/api/prefill?org=${oid}${pid ? `&product=${pid}` : ''}`).then(r => {
      setPre(r.fields);
      setFields(f => {  // refill only what the user has not typed themselves
        const next = { ...f };
        Object.entries(r.fields).forEach(([k, v]) => { if (!f[k] || f[k] === pre[k]?.value) next[k] = v.value; });
        return next;
      });
    }).catch(e => setErr(e.message));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [oid, pid]);
  if (!orgs.data) return <Loading err={orgs.err} />;
  const o = detail.data;
  const products = (o?.products || []).filter(p => p.status === 'approved');
  const drafts = (o?.products || []).filter(p => p.status === 'draft');
  return (
    <>
      <Crumbs items={[o && [o.name, `#/orgs/${o.id}/campaigns`], ['New campaign']]} />
      <div className="page" style={{ maxWidth: 940 }}>
        <Eyebrow>New campaign</Eyebrow>
        <h1>What is this campaign <em className="s">for?</em></h1>
        <p className="lead">We pre-fill what we already know from the organization and product, and show where each value came from. Changes here apply to this campaign only.</p>
        <div className="card">
          <div className="fields">
            <div><label className="f" htmlFor="c-org">Organization</label>
              <select id="c-org" value={oid} onChange={e => { setOid(e.target.value); setPid(''); }}>
                <option value="">Choose…</option>{orgs.data.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
            <div><label className="f" htmlFor="c-prod">Product or service</label>
              <select id="c-prod" value={pid} onChange={e => setPid(e.target.value)} disabled={!oid}>
                <option value="">The whole organization</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
              {drafts.length > 0 && <div className="from changed">{drafts.length} researched product{drafts.length > 1 ? 's' : ''} need approval first · <a href={`#/orgs/${oid}/products`}>review</a></div>}</div>
            <Field wide label="Campaign name" value={name} onChange={setName} placeholder="Xbox holiday subscription" id="c-name" />
          </div>
          {oid && <CampaignForm fields={fields} setFields={setFields} pre={pre} objective={objective} setObjective={setObjective} />}
          <Err>{err}</Err>
          <div className="actions">
            <Act className="btn" busy="Creating…" disabled={!oid || !name.trim() || !objective} onError={setErr} run={async () => {
              const c = await api.post('/api/campaigns', { org_id: oid, product_id: pid || null, name, fields: { ...fields, objective } });
              go(`/campaigns/${c.id}/brief`);
            }}>Create campaign</Act>
            <span className="note">{!objective ? 'Choose an objective to continue.' : 'Next: we prepare the brief for you to check.'}</span>
          </div>
        </div>
      </div>
    </>
  );
}
