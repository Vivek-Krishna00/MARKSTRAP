import { useRef, useState } from 'react';
import { api, C } from '../api.js';
import { go } from '../router.js';
import { METRICS } from '../copy.js';
import { Act, Empty, Err, Loading, Section, Sim, toast, useLoad } from '../ui.jsx';

function Entry({ it, metrics, set, row }) {
  const rest = Object.keys(METRICS).filter(m => !metrics.includes(m));
  const input = m => (
    <div key={m}><label className="f" htmlFor={`m-${it.id}-${m}`}>{METRICS[m]}</label>
      <input id={`m-${it.id}-${m}`} inputMode="decimal" value={row[m] || ''} onChange={e => set(m, e.target.value)} placeholder="0" /></div>
  );
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="row between"><h4 style={{ margin: 0 }}>{it.name}</h4><span className="tag ice">{it.platform}</span></div>
      <div className="grid three">{metrics.map(input)}</div>
      <details><summary>Other numbers</summary><div className="grid three">{rest.map(input)}
        <div><label className="f" htmlFor={`m-${it.id}-aud`}>Audience <small>if the platform splits it</small></label>
          <input id={`m-${it.id}-aud`} value={row.audience || ''} onChange={e => set('audience', e.target.value)} placeholder="18–24" /></div></div></details>
    </div>
  );
}

function Comparison({ r }) {
  return (
    <>
      <Section>What the simulation predicted, and what happened</Section>
      <div className="card ice"><p style={{ margin: 0 }}><b>Real results carry more weight than predictions.</b> Where they disagree, reality wins: the simulated audience learns from it and future concepts follow what really worked.</p></div>
      <div className="scroll-x" style={{ marginTop: 14 }}><table className="compare">
        <thead><tr><th>Concept</th><th>Predicted rank <Sim>sim</Sim></th><th>Real rank</th><th>Real vs this campaign</th><th>Verdict</th></tr></thead>
        <tbody>{r.concepts.map(p => (
          <tr key={p.id}><td>{p.name}<div className="note">{p.platform}</div></td><td className="num">#{p.predicted_rank}</td><td className="num">#{p.real_rank}</td>
            <td className="num" style={{ color: p.real_score > 0 ? 'var(--good)' : p.real_score < 0 ? 'var(--bad)' : undefined }}>{p.real_score > 0 ? '+' : ''}{p.real_score.toFixed(2)}σ</td>
            <td><span className={`tag ${p.verdict.startsWith('Simulation') ? 'warn' : p.verdict.startsWith('Roughly') ? 'good' : ''}`}>{p.verdict}</span></td></tr>
        ))}</tbody></table></div>
      <div className="grid two" style={{ marginTop: 14 }}>
        <div className="card">
          <h4>Where the simulation was right</h4>
          {r.right.length ? <ul className="clean plus">{r.right.map(x => <li key={x}>{x}</li>)}</ul> : <p className="note">{r.tested < 3 ? 'Too few results to say.' : 'Nowhere clearly.'}</p>}
          <h4 style={{ marginTop: 14 }}>Where it was wrong</h4>
          {r.wrong.length ? <ul className="clean minus">{r.wrong.map(x => <li key={x}>{x}</li>)}</ul> : <p className="note">{r.tested < 3 ? 'Too few results to say.' : 'No clear misses.'}</p>}
          <p className="note">{r.rank_agreement == null ? 'Ranking agreement needs at least 3 tested concepts.' : `Ranking agreement: ${r.rank_agreement} (1 = same order, 0 = unrelated, −1 = reversed).`}
            {' '}{r.top_match ? 'It picked the real winner.' : `It expected “${r.top_predicted}” to win; “${r.top_real}” did.`}</p>
        </div>
        <div className="card">
          <dl className="kv">
            <dt>Best concept</dt><dd>{r.best_concept}</dd>
            <dt>Best message approach</dt><dd>{r.best_message ? `${r.best_message.name}${r.best_message.others ? '' : ' (only one tested)'}` : '—'}</dd>
            <dt>Best visual direction</dt><dd>{r.best_visual ? `${r.best_visual.name}${r.best_visual.others ? '' : ' (only one tested)'}` : '—'}</dd>
            <dt>Best audience</dt><dd>{r.best_audience ? r.best_audience.name : 'Not measured'}</dd>
          </dl>
          <h4 style={{ marginTop: 14 }}>Still uncertain</h4>
          <ul className="clean">{r.uncertain.map((u, i) => <li key={i} className="note">{u}</li>)}</ul>
        </div>
      </div>
    </>
  );
}

export default function Results({ cid, c, reload: reloadCampaign }) {
  const q = useLoad(() => Promise.all([api.get(`${C(cid)}/launch`), api.get(`${C(cid)}/reality`)]), [cid]);
  const [rows, setRows] = useState({});
  const [err, setErr] = useState('');
  const file = useRef(null);
  if (!q.data) return <Loading err={q.err} />;
  const [L, real] = q.data;
  const reload = async () => { await q.reload(); reloadCampaign(); };
  const set = id => (k, v) => setRows(x => ({ ...x, [id]: { ...(x[id] || {}), [k]: v } }));
  const filled = Object.entries(rows).filter(([, r]) => Object.entries(r).some(([k, v]) => k !== 'audience' && String(v).trim()));
  return (
    <div className="cols">
      <div>
        <h2>What <em className="s">really</em> happened.</h2>
        <p className="lead">Enter the numbers from each platform. For a {c.fields.objective || 'campaign'} objective, the first fields matter most. A weak result for one creative is not proof the offer has no market.</p>
        {L.items.length ? <>
          {L.items.map(it => <Entry key={it.id} it={it} metrics={L.measure.metrics} row={rows[it.id] || {}} set={set(it.id)} />)}
          <Err>{err}</Err>
          <div className="actions">
            <Act className="btn" disabled={!filled.length} busy="Saving…" onError={setErr} run={async () => {
              await api.post(`${C(cid)}/results/rows`, { rows: filled.map(([id, r]) => ({ ad_id: id, platform: L.items.find(i => i.id === id)?.platform, ...r })) });
              setRows({}); await reload(); toast('Results saved. Reality now outweighs the simulation for these concepts.');
            }}>Save results</Act>
            <button className="line" onClick={() => file.current.click()}>Or upload the results sheet</button>
            <input ref={file} type="file" accept=".csv" hidden onChange={async e => {
              setErr('');
              try { await api.form(`${C(cid)}/results`, { file: e.target.files[0] }); await reload(); toast('Results imported'); } catch (x) { setErr(x.message); }
            }} />
          </div>
        </> : <Empty>Approve and publish concepts first.</Empty>}

        {real.tested > 0 ? <>
          <Comparison r={real} />
          <div className="actions"><Act className="btn" busy="Reading the results…" onError={setErr} run={async () => { await api.post(`${C(cid)}/next`); await reloadCampaign(); go(`/campaigns/${cid}/next`); }}>
            Recommend the next experiment</Act></div>
        </> : <p className="note" style={{ marginTop: 20 }}>The comparison appears once results are in.</p>}
      </div>
      <aside>
        <div className="card"><h4>Which numbers matter</h4>
          <div className="tags">{L.measure.metrics.map(m => <span key={m} className="tag ice">{METRICS[m] || m}</span>)}</div>
          <p className="note">Scores use ratios (saves per reach, sign-ups per impression), not raw counts, and are compared with this campaign's own results.</p></div>
      </aside>
    </div>
  );
}
