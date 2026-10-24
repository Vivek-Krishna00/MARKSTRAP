import { api, C } from '../api.js';
import { STEPS } from '../copy.js';
import { Crumbs, Loading, useLoad } from '../ui.jsx';
import Brief from './Brief.jsx';
import Concepts from './Concepts.jsx';
import Assets from './Assets.jsx';
import Reel from './Reel.jsx';
import Launch from './Launch.jsx';
import Results from './Results.jsx';
import Next from './Next.jsx';

export default function Campaign({ cid, step, sub }) {
  const q = useLoad(() => api.get(C(cid)), [cid], { poll: 2500, active: d => d?.busy });
  const c = q.data;
  if (!c) return <Loading err={q.err} />;
  const cur = step === 'reels' ? 'assets' : step || c.where || 'brief';
  const reelsOk = c.reels.filter(r => c.approved.includes(r.ad_id)).every(r => c.reel_approvals[r.id]);
  const done = {
    brief: c.brief_status === 'confirmed', concepts: c.approved.length > 0, assets: c.approved.length > 0 && reelsOk,
    launch: !!c.published_at, results: c.results_count > 0, next: c.insights.length > 0,
  };
  const View = { brief: Brief, concepts: Concepts, assets: Assets, launch: Launch, results: Results, next: Next }[cur] || Brief;
  return (
    <>
      <Crumbs items={[[c.org.name, `#/orgs/${c.org.id}/campaigns`], c.product && [c.product.name, `#/orgs/${c.org.id}/products/${c.product.id}`], [c.name]]} />
      <div className="page">
        <div className="row between" style={{ alignItems: 'flex-end', marginBottom: 18 }}>
          <div>
            <div className="kicker">Campaign · {c.fields.objective || 'no objective yet'}</div>
            <h1 style={{ marginTop: 6 }}>{c.name}</h1>
          </div>
          <div className="row"><span className={`tag ${c.todo ? 'warn' : 'ice'}`}>{c.stage}</span>{c.busy && <span className="tag ice pulse">working</span>}</div>
        </div>
        <nav className="steps" aria-label="Campaign steps">
          {STEPS.map(([k, label], i) => (
            <a key={k} href={`#/campaigns/${cid}/${k}`} className={`${cur === k ? 'on' : ''} ${done[k] && cur !== k ? 'done' : ''}`} aria-current={cur === k ? 'step' : undefined}>
              <i>{done[k] && cur !== k ? '✓' : i + 1}</i>{label}
            </a>
          ))}
        </nav>
        {step === 'reels' && sub ? <Reel cid={cid} rid={sub} c={c} reload={q.reload} /> : <View cid={cid} c={c} reload={q.reload} />}
      </div>
    </>
  );
}
