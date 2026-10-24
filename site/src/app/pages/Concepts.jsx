import { useState } from 'react';
import { api, C } from '../api.js';
import { REACTIONS } from '../copy.js';
import { Act, Empty, Err, Eyebrow, Loading, Section, Sim, pct, toast, useLoad } from '../ui.jsx';

const COLORS = { share: 'var(--r-share)', engage: 'var(--r-engage)', ignore: 'var(--r-ignore)', dislike: 'var(--r-dislike)' };
const FIT = { yes: ['good', 'Follows it'], partly: ['warn', 'Partly'], no: ['bad', 'Does not follow it'] };
const DECISION = { approved: ['solid', 'Approved'], saved: ['ice', 'Saved for later'], rejected: ['bad', 'Rejected'], revise: ['warn', 'Revision requested'] };
const PART_LABEL = { main_idea: 'Main idea', headline: 'Headline', body: 'Caption', visual: 'Visual direction', format: 'Format', platform: 'Platform', post_time: 'Posting time' };

const Fit = ({ v }) => (v ? <span className={`tag ${FIT[v]?.[0] || ''}`}>{FIT[v]?.[1] || v}</span> : <span className="note">not reviewed yet</span>);

function Groups({ a }) {
  if (!a.groups.length) return <p className="note">Too few simulated people per group to compare.</p>;
  return (
    <div>
      {a.groups.slice(0, 8).map(g => (
        <div key={g.group} className="groupbar">
          <span>{g.group} <span className="note">· {g.people}</span></span>
          <span className="t"><i className={g.response < 0 ? 'neg' : ''} style={g.response < 0 ? { left: `${50 + g.response * 50}%`, right: '50%' } : { width: `${g.response * 50}%` }} /></span>
          <b>{g.response > 0 ? '+' : ''}{g.response.toFixed(2)}</b>
        </div>
      ))}
      {a.disagreement && <p className="note" style={{ marginBottom: 0 }}>Biggest disagreement: <b>{a.disagreement.liked}</b> responded well, <b>{a.disagreement.disliked}</b> did not.</p>}
    </div>
  );
}

function Concept({ k, cid, reload, selected, toggle }) {
  const [mode, setMode] = useState('');
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const c = k.content, s = k.score, rv = k.review, n = s.counts;
  const tot = s.people || 1;
  const decide = async (status, feedback = '') => { await api.post(`${C(cid)}/concepts/${k.id}/decision`, { status, feedback }); await reload(); };
  const quote = k.reasons.copy[0];
  return (
    <article className={`concept ${k.decision}`} aria-label={c.concept_name || c.headline}>
      <div>
        <div className="tags">
          {k.decision && <span className={`tag ${DECISION[k.decision][0]}`}>{DECISION[k.decision][1]}</span>}
          {k.recommended ? <span className="tag good">Recommended for a real test</span> : <span className="tag">Not recommended yet</span>}
          <span className="tag ice">{c.platform}</span><span className="tag">{c.format || 'post'}</span>{c.post_time && <span className="tag">{c.post_time}</span>}
          {k.revised_from && <span className="tag">revised</span>}{k.combined_from && <span className="tag">combined</span>}
        </div>
        <div className="kicker" style={{ marginTop: 12 }}>{c.concept_name || 'Concept'}</div>
        <h3>{c.headline}</h3>
        {c.main_idea && <p className="idea">{c.main_idea}</p>}
        <p className="muted" style={{ marginTop: 0 }}>{c.body}</p>
        <div className="visual">VISUAL — {c.visual}{c.font ? `\nTYPE — ${c.font}` : ''}</div>
        <dl className="kv" style={{ marginTop: 14 }}>
          {c.emotion && <><dt>Should feel</dt><dd>{c.emotion}</dd></>}
          {c.why_it_may_work && <><dt>Why it may work</dt><dd>{c.why_it_may_work}</dd></>}
          {c.risks && <><dt>Weaknesses or risks</dt><dd>{c.risks}</dd></>}
          <dt>Approach</dt><dd>{[k.approach.message, k.approach.visual].filter(Boolean).join(' · ')}</dd>
        </dl>

        <details>
          <summary>Why it scored this way</summary>
          <ul className="clean" style={{ marginTop: 8 }}>{s.why.map((w, i) => <li key={i}>{w}</li>)}</ul>
          <p className="note">Confidence: <b>{s.confidence}</b>. {s.confidence_note} {s.limits}</p>
        </details>
        <details>
          <summary>Which audience groups responded</summary>
          <div style={{ marginTop: 10 }}><Sim>Simulated groups</Sim></div>
          <div className="grid two" style={{ marginTop: 10 }}>
            <div><div className="label">Positive</div>{k.audience.positive.length ? k.audience.positive.map(g => <p key={g.group} className="ok" style={{ margin: '4px 0' }}>+ {g.group}</p>) : <p className="note">No group stood out.</p>}</div>
            <div><div className="label">Negative</div>{k.audience.negative.length ? k.audience.negative.map(g => <p key={g.group} style={{ margin: '4px 0', color: 'var(--bad)' }}>− {g.group}</p>) : <p className="note">No group stood out.</p>}</div>
          </div>
          <div style={{ marginTop: 10 }}><Groups a={k.audience} /></div>
        </details>
        <details>
          <summary>Reactions to the message, visual, format and platform</summary>
          {rv ? <dl className="kv" style={{ marginTop: 10 }}>
            <dt>Overall</dt><dd>{rv.summary}</dd>
            <dt>Message</dt><dd>{rv.message}</dd><dt>Visual idea</dt><dd>{rv.visual}</dd>
            <dt>Format</dt><dd>{rv.format}</dd><dt>Platform</dt><dd>{rv.platform}</dd>
          </dl> : <p className="note">Get the review to see this.</p>}
          {rv && <div className="grid two" style={{ marginTop: 12 }}>
            <div><div className="label">Liked</div><ul className="clean plus">{(rv.positives || []).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div><div className="label">Disliked</div><ul className="clean minus">{(rv.negatives || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
              {(rv.ignored_because || []).length > 0 && <><div className="label" style={{ marginTop: 10 }}>Why people would scroll past</div>
                <ul className="clean minus">{rv.ignored_because.map((x, i) => <li key={i}>{x}</li>)}</ul></>}</div>
          </div>}
          {k.reasons.visual.length > 0 && <div style={{ marginTop: 12 }}>{k.reasons.visual.slice(0, 2).map((r, i) => <p key={i} className="quote">“{r.why}”<small>— {r.persona}, simulated · on the visual</small></p>)}</div>}
        </details>
        <details open={!!rv && (rv.brief_fit === 'no' || rv.brand_fit === 'no' || (rv.human_review || []).length > 0)}>
          <summary>Brief, brand rules and human review</summary>
          <dl className="kv" style={{ marginTop: 10 }}>
            <dt>Follows the brief</dt><dd><Fit v={rv?.brief_fit} /> {rv?.brief_notes}</dd>
            <dt>Follows brand rules</dt><dd><Fit v={rv?.brand_fit} /> {rv?.brand_notes}</dd>
          </dl>
          {(rv?.human_review || []).length > 0 && <div className="card warn tight" style={{ marginTop: 10 }}><b>A person must check before this goes live</b>
            <ul className="clean">{rv.human_review.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
        </details>
        {k.variations.length > 0 && <details>
          <summary>{k.variations.length} experimental variation{k.variations.length > 1 ? 's' : ''} of this idea</summary>
          <ul className="clean" style={{ marginTop: 8 }}>{k.variations.map(v => <li key={v.id}>{v.headline} <span className="note">· {Math.round(v.score * 100)}</span></li>)}</ul>
        </details>}

        {mode && <div style={{ marginTop: 16 }}>
          <label className="f" htmlFor={`fb-${k.id}`}>{mode === 'revise' ? 'What should change?' : 'Your feedback'}</label>
          <textarea id={`fb-${k.id}`} rows={2} value={text} onChange={e => setText(e.target.value)}
            placeholder={mode === 'revise' ? 'Make it about families on the sofa; keep the headline short' : 'Notes for the team'} />
          <div className="row" style={{ marginTop: 8 }}>
            {mode === 'revise'
              ? <Act className="btn tiny" busy="Revising and testing…" disabled={!text.trim()} onError={setErr} run={async () => {
                await api.post(`${C(cid)}/concepts/${k.id}/revise`, { feedback: text }); setMode(''); setText(''); await reload(); toast('Revised concept added and tested');
              }}>Revise and test</Act>
              : <Act className="btn tiny" disabled={!text.trim()} onError={setErr} run={async () => { await decide(k.decision, text); setMode(''); setText(''); toast('Feedback saved'); }}>Save feedback</Act>}
            <button className="line tiny" onClick={() => setMode('')}>Cancel</button>
          </div>
        </div>}
        <Err>{err}</Err>
        <div className="actions" style={{ marginTop: 18 }}>
          {k.decision === 'approved'
            ? <><a className="btn tiny" href={`#/campaigns/${cid}/assets`}>Create assets →</a><Act className="line tiny" run={() => decide('')}>Undo approval</Act></>
            : <Act className="btn tiny" run={() => decide('approved')}>Approve</Act>}
          {k.decision !== 'saved' && k.decision !== 'approved' && <Act className="line tiny" run={() => decide('saved')}>Save for later</Act>}
          {k.decision === 'rejected' ? <Act className="line tiny" run={() => decide('')}>Undo reject</Act>
            : k.decision !== 'approved' && <Act className="line tiny danger" run={() => decide('rejected')}>Reject</Act>}
          <button className="line tiny" onClick={() => setMode('revise')}>Request revision</button>
          <button className="line tiny" onClick={() => setMode('feedback')}>Add feedback</button>
          {!rv && <Act className="line tiny" busy="Reviewing…" onError={setErr} run={async () => { await api.post(`${C(cid)}/concepts/${k.id}/review`); await reload(); }}>Get the full review</Act>}
          <label className="chk"><input type="checkbox" checked={selected} onChange={toggle} /> Compare</label>
        </div>
      </div>

      <div className="meter">
        <Sim>Simulated response</Sim>
        <div className="big" style={{ marginTop: 10 }}>{pct(n.share, tot)}%<small>would share</small></div>
        <div className="react" aria-hidden="true">{Object.entries(n).map(([r, v]) => <i key={r} style={{ width: `${(v / tot) * 100}%`, background: COLORS[r] }} />)}</div>
        <div className="note">{n.engage} engage · {n.ignore} scroll past · {n.dislike} annoyed</div>
        <div className="note" style={{ marginTop: 6 }}>{s.people} simulated people · confidence {s.confidence.toLowerCase()}</div>
        {rv?.summary && <p style={{ margin: '12px 0 0', fontSize: 14 }}>{rv.summary}</p>}
        {quote && <p className="quote" style={{ marginTop: 12 }}>“{quote.why}”<small>— {quote.persona}, simulated</small></p>}
      </div>
    </article>
  );
}

function Compare({ list }) {
  const rows = [
    ['Main idea', k => k.content.main_idea], ['Headline', k => k.content.headline],
    ['Platform · format', k => `${k.content.platform} · ${k.content.format || 'post'}`], ['Should feel', k => k.content.emotion],
    ['Would share (simulated)', k => `${pct(k.score.counts.share, k.score.people)}%`], ['Confidence', k => k.score.confidence],
    ['Recommended for a real test', k => (k.recommended ? 'Yes' : 'Not yet')],
    ['Follows the brief', k => <Fit v={k.review?.brief_fit} />], ['Follows brand rules', k => <Fit v={k.review?.brand_fit} />],
    ['Responded well', k => k.audience.positive.map(g => g.group).join(', ') || '—'],
    ['Responded badly', k => k.audience.negative.map(g => g.group).join(', ') || '—'],
    ['Risks', k => k.content.risks], ['Needs human review', k => (k.review?.human_review || []).join('; ') || '—'],
  ];
  return (
    <div className="scroll-x"><table className="compare">
      <thead><tr><th scope="col"> </th>{list.map(k => <th key={k.id} scope="col">{k.content.concept_name || k.content.headline}</th>)}</tr></thead>
      <tbody>{rows.map(([label, fn]) => <tr key={label}><th scope="row">{label}</th>{list.map(k => <td key={k.id}>{fn(k)}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

function Combine({ list, parts, cid, reload, done }) {
  const [pick, setPick] = useState(() => Object.fromEntries(parts.map((p, i) => [p, list[i < 3 ? 0 : 1]?.id || list[0].id])));
  const [err, setErr] = useState('');
  return (
    <div className="card ice" style={{ marginTop: 16 }}>
      <h4>Combine the best parts</h4>
      <p className="note" style={{ marginTop: 0 }}>Pick each part from one of the selected concepts. We join them into one concept and test it on the same simulated audience.</p>
      <div className="fields">{parts.map(p => (
        <div key={p}><label className="f" htmlFor={`cb-${p}`}>{PART_LABEL[p] || p}</label>
          <select id={`cb-${p}`} value={pick[p]} onChange={e => setPick(x => ({ ...x, [p]: e.target.value }))}>
            {list.map(k => <option key={k.id} value={k.id}>{k.content.concept_name || k.content.headline}: {String(k.content[p] || '').slice(0, 50)}</option>)}
          </select></div>
      ))}</div>
      <Err>{err}</Err>
      <div className="actions"><Act className="btn" busy="Combining and testing…" onError={setErr} run={async () => {
        await api.post(`${C(cid)}/concepts/combine`, { parts: pick }); await reload(); done(); toast('Combined concept added and tested');
      }}>Combine and test</Act></div>
    </div>
  );
}

export default function Concepts({ cid, c, reload: reloadCampaign }) {
  const q = useLoad(() => api.get(`${C(cid)}/concepts`), [cid], { poll: 2500, active: d => d?.busy });
  const [sel, setSel] = useState([]);
  const [view, setView] = useState('');
  if (c.brief_status !== 'confirmed') {
    return <Empty>Concepts are made after you confirm the brief. <a href={`#/campaigns/${cid}/brief`}>Go to the brief</a></Empty>;
  }
  const d = q.data;
  if (!d) return <Loading err={q.err} />;
  const reload = async () => { await q.reload(); reloadCampaign(); };
  const p = d.progress || {};
  const list = d.concepts;
  const chosen = list.filter(k => sel.includes(k.id));
  const toggle = id => () => setSel(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id].slice(-3)));
  const approved = list.filter(k => k.decision === 'approved').length;
  return (
    <div>
      <Eyebrow>Step 2 · Concepts</Eyebrow>
      <h2>Ideas, given a <em className="s">fair test.</em></h2>
      <p className="lead">{list.length} distinct concepts, each tested on {d.people} simulated people. {d.limits}</p>

      {(d.busy || p.error) && <div className={`card ${p.error ? 'warn' : 'ice'}`} style={{ marginBottom: 18 }}>
        {d.busy ? <>
          <div className="row between"><b className="pulse">{p.step || 'Working'}…</b><span className="note">round {Math.min((p.done || 0) + 1, p.total || 1)} of {p.total}</span></div>
          <div className="stagebar" style={{ marginTop: 10 }}><i style={{ width: `${((p.done || 0) / (p.total || 1)) * 100}%` }} /></div>
          <p className="note" style={{ marginBottom: 0 }}>Creative specialists draft competing approaches; the simulated audience reacts; the strongest patterns are developed further. You can leave this page.</p>
        </> : <><b>Concept generation stopped.</b> <span className="note">{p.error}</span>
          <div className="actions" style={{ marginTop: 10 }}><Act className="btn tiny" run={async () => { await api.post(`${C(cid)}/explore?rounds=2`); await reload(); }}>Try again</Act></div></>}
      </div>}

      <div className="row between" style={{ marginBottom: 14 }}>
        <div className="legend">{Object.entries(REACTIONS).map(([r, l]) => <span key={r}><i style={{ background: COLORS[r] }} />{l}</span>)}</div>
        <Sim>All scores are simulated</Sim>
      </div>

      {list.length ? list.map(k => <div key={k.id} style={{ marginBottom: 14 }}><Concept k={k} cid={cid} reload={reload} selected={sel.includes(k.id)} toggle={toggle(k.id)} /></div>)
        : !d.busy && <Empty>No concepts yet.</Empty>}

      {view === 'compare' && chosen.length > 1 && <><Section>Side by side</Section><Compare list={chosen} /></>}
      {view === 'combine' && chosen.length > 1 && <Combine list={chosen} parts={d.parts} cid={cid} reload={reload} done={() => { setView(''); setSel([]); }} />}

      {(chosen.length > 0 || approved > 0) && (
        <div className="sticky-bar">
          {chosen.length > 0 && <>
            <span className="note">{chosen.length} selected</span>
            <button className="line tiny" disabled={chosen.length < 2} onClick={() => setView(view === 'compare' ? '' : 'compare')}>Compare</button>
            <button className="line tiny" disabled={chosen.length < 2} onClick={() => setView(view === 'combine' ? '' : 'combine')}>Combine parts</button>
            <button className="link" onClick={() => { setSel([]); setView(''); }}>Clear</button>
          </>}
          {approved > 0 && <a className="btn tiny" style={{ marginLeft: 'auto' }} href={`#/campaigns/${cid}/assets`}>Create assets for {approved} approved →</a>}
        </div>
      )}
      <div className="actions">
        <Act className="line" disabled={d.busy} run={async () => { await api.post(`${C(cid)}/explore?rounds=2`); await reload(); }}>Develop 2 more rounds</Act>
        <span className="note">You make the final decision. Rejected ideas are kept; real results can bring them back.</span>
      </div>
    </div>
  );
}
