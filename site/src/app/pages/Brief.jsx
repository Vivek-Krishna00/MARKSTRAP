import { Fragment, useEffect, useState } from 'react';
import { api, C } from '../api.js';
import { go } from '../router.js';
import { BRIEF_FIELDS, CAMPAIGN_FIELDS } from '../copy.js';
import { Act, Empty, Err, Eyebrow, Section, toast } from '../ui.jsx';
import { CampaignForm } from './CampaignNew.jsx';

const BASIS = { organization: 'from the organization profile', product: 'from the product', campaign: 'from your campaign requirements' };
const LISTS = ['evidence'];

function Basis({ b }) {
  if (!b) return null;
  if (b === 'assumption') return <span className="prov unconfirmed" title="Not stated anywhere in what you gave us">Assumption</span>;
  return <span className="from">↳ {BASIS[b] || b}</span>;
}

function Requirements({ c, cid, reload }) {
  const [edit, setEdit] = useState(false);
  const [fields, setFields] = useState(c.fields);
  const [objective, setObjective] = useState(c.fields.objective || '');
  const filled = Object.entries(c.fields).filter(([k, v]) => v && k !== 'objective');
  if (edit) {
    return (
      <div className="card">
        <CampaignForm fields={fields} setFields={setFields} objective={objective} setObjective={setObjective}
          pre={Object.fromEntries(Object.entries(c.field_sources).map(([k, from]) => [k, { from, value: c.fields[k] }]))} />
        <div className="actions">
          <Act className="btn" run={async () => { await api.patch(C(cid), { fields: { ...fields, objective } }); await reload(); setEdit(false); toast('Requirements saved for this campaign'); }}>Save requirements</Act>
          <button className="line" onClick={() => setEdit(false)}>Cancel</button>
        </div>
      </div>
    );
  }
  return (
    <div className="card">
      <div className="row between"><h4>Campaign requirements</h4><button className="link" onClick={() => setEdit(true)}>Edit</button></div>
      {filled.length ? <dl className="kv">{filled.map(([k, v]) => <Fragment key={k}><dt>{CAMPAIGN_FIELDS[k]?.[0] || k}</dt>
        <dd>{String(v)}{c.field_sources[k] && <div className="from">↳ {c.field_sources[k]}</div>}</dd></Fragment>)}</dl>
        : <p className="note">Only the objective so far. Add the goal, audience, offer and rules for a sharper brief.</p>}
    </div>
  );
}

export default function Brief({ cid, c, reload }) {
  const [b, setB] = useState(c.brief || {});
  const [answers, setAnswers] = useState('');
  const [err, setErr] = useState('');
  useEffect(() => { setB(c.brief || {}); }, [c.brief]);
  const status = c.brief_status;
  const set = k => v => setB(x => ({ ...x, [k]: LISTS.includes(k) ? v.split('\n') : v }));
  const val = k => (LISTS.includes(k) ? (b[k] || []).join('\n') : b[k] || '');

  if (status === 'none') {
    return (
      <div className="cols">
        <div>
          <Eyebrow>Step 1 · Brief</Eyebrow>
          <h2>Let's write the <em className="s">brief.</em></h2>
          <p className="lead">We combine your approved organization profile, the product and these requirements into one clear brief. You check it before any ideas are made.</p>
          <Requirements c={c} cid={cid} reload={reload} />
          <Err>{err}</Err>
          <div className="actions">
            <Act className="btn" busy="Writing the brief…" onError={setErr} run={async () => { await api.post(`${C(cid)}/brief`); await reload(); }}>Prepare the brief</Act>
            <span className="note">Usually under a minute.</span>
          </div>
        </div>
        <aside><div className="card"><h4>Only approved information</h4><p className="note">Research findings reach the brief only after you approve them. Anything we have to assume is labelled as an assumption.</p></div></aside>
      </div>
    );
  }

  const confirmed = status === 'confirmed';
  const dirty = JSON.stringify(b) !== JSON.stringify(c.brief);
  return (
    <div className="cols">
      <div>
        <Eyebrow>{confirmed ? 'Confirmed brief' : 'Brief to confirm'}</Eyebrow>
        <h2>{confirmed ? <>The brief is <em className="s">set.</em></> : <>Here's what we <em className="s">understood.</em></>}</h2>
        <p className="lead">{confirmed ? 'Concepts follow this brief. Editing it and confirming again starts the concepts over; what you learned from real results is kept.'
          : 'Correct anything that is off. Concepts are made only after you confirm.'}</p>

        {!confirmed && (b.missing || []).length > 0 && (
          <div className="card warn" style={{ marginBottom: 20 }}>
            <h4>Only these details block the campaign</h4>
            {b.missing.map((m, i) => <p key={i} className="big-q" style={{ fontSize: 17 }}>{m}</p>)}
            <textarea rows={2} value={answers} onChange={e => setAnswers(e.target.value)} aria-label="Your answers"
              placeholder="Answer here, or leave blank and we'll work with what we have" />
          </div>
        )}

        <div className="card">
          {Object.entries(BRIEF_FIELDS).map(([k, label]) => (
            <div key={k}>
              <label className="f" htmlFor={`b-${k}`}>{label}{LISTS.includes(k) && <small>one per line</small>}</label>
              {k === 'objective' ? <input id={`b-${k}`} value={c.fields.objective || ''} disabled />
                : <textarea id={`b-${k}`} rows={LISTS.includes(k) || k === 'creative_direction' ? 3 : 2} value={val(k)} disabled={confirmed} onChange={e => set(k)(e.target.value)} />}
              <Basis b={(b.basis || {})[k]} />
            </div>
          ))}
        </div>

        {(b.assumptions || []).length > 0 && <>
          <Section count={b.assumptions.length}>Assumptions we made</Section>
          <div className="card"><ul className="clean">{b.assumptions.map((a, i) => <li key={i}>{a} <span className="prov unconfirmed">Assumption</span></li>)}</ul>
            <p className="note" style={{ marginBottom: 0 }}>Correct them in the fields above or in your answers.</p></div>
        </>}
        {b.client_answers && <p className="note">Your answers: {b.client_answers}</p>}

        <Err>{err}</Err>
        <div className="actions">
          {confirmed ? <>
            <a className="btn" href={`#/campaigns/${cid}/concepts`}>Go to concepts</a>
            <Act className="line" run={async () => { await api.put(`${C(cid)}/brief`, { brief: {} }); await reload(); }}>Edit the brief</Act>
          </> : <>
            <Act className="btn" busy="Preparing the simulated audience…" onError={setErr} run={async () => {
              await api.post(`${C(cid)}/brief/confirm`, { brief: { ...b, evidence: (b.evidence || []).filter(x => x.trim()) }, answers });
              await api.post(`${C(cid)}/explore?rounds=3`);
              await reload();
              go(`/campaigns/${cid}/concepts`);
            }}>Confirm brief and create concepts</Act>
            {dirty && <Act className="line" run={async () => { await api.put(`${C(cid)}/brief`, { brief: b }); await reload(); toast('Draft saved'); }}>Save draft</Act>}
            <Act className="line" busy="Rewriting…" onError={setErr} run={async () => { await api.post(`${C(cid)}/brief`); await reload(); }}>Rewrite from requirements</Act>
          </>}
        </div>
      </div>
      <aside>
        <Requirements c={c} cid={cid} reload={reload} />
        <div className="card"><h4>What happens next</h4><p className="note">Creative specialists draft distinct concepts. A simulated audience, sampled from real personality data, reacts to each one. The strongest approaches are developed further over three rounds.</p></div>
        {!confirmed && !(b.missing || []).length && <Empty>Nothing blocks this brief.</Empty>}
      </aside>
    </div>
  );
}
