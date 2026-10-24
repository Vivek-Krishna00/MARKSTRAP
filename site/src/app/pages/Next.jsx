import { api, C } from '../api.js';
import { go } from '../router.js';
import { Act, Empty, Eyebrow, Section, when } from '../ui.jsx';

const List = ({ title, items, kind = '' }) => (
  <div><div className="label" style={{ margin: '14px 0 6px' }}>{title}</div>
    {(items || []).length ? <ul className={`clean ${kind}`}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="note">Nothing yet.</p>}</div>
);

export default function Next({ cid, c, reload }) {
  const ins = c.insights[0];
  if (!ins) {
    return <Empty>Add real results first; the next experiment is based on what really happened. <a href={`#/campaigns/${cid}/results`}>Go to results</a></Empty>;
  }
  const n = ins.next || {};
  return (
    <div className="cols">
      <div>
        <Eyebrow>Step 6 · Next experiment</Eyebrow>
        <h2>One change, <em className="s">clearly tested.</em></h2>
        <p className="lead">Changing many things at once makes the next result impossible to read. This experiment changes one thing and keeps the rest the same.</p>
        <div className="card ice">
          <div className="kicker">Hypothesis</div>
          <p className="big-q" style={{ marginTop: 8 }}>{n.hypothesis}</p>
          <dl className="kv">
            <dt>The one change</dt><dd><b>{n.change}</b></dd>
            <dt>Audience</dt><dd>{n.audience}</dd><dt>Channel</dt><dd>{n.channel}</dd><dt>Success looks like</dt><dd>{n.success_metric}</dd>
          </dl>
          <List title="Keep exactly the same" items={n.keep_same} />
          <div className="actions">
            <Act className="btn" disabled={c.busy} busy="Starting…" run={async () => { await api.post(`${C(cid)}/explore?rounds=2`); await reload(); go(`/campaigns/${cid}/concepts`); }}>Run this experiment</Act>
            <span className="note">New concepts follow this hypothesis; you approve them as before.</span>
          </div>
        </div>
        <Section>What the evidence says</Section>
        <div className="card">
          <div className="grid two">
            <List title="What worked" items={ins.what_worked} kind="plus" />
            <List title="What did not" items={ins.what_didnt} kind="minus" />
          </div>
          <List title="What the evidence does not prove" items={ins.not_proven} />
          {ins.caution && <p className="note" style={{ marginBottom: 0 }}>{ins.caution}</p>}
        </div>
      </div>
      <aside>
        <div className="card"><h4>Earlier experiments <span className="count">{c.insights.length}</span></h4>
          {c.insights.map((x, i) => <p key={i} className="note" style={{ margin: '8px 0 0' }}>{x.at ? when(x.at) : `Round ${x.term}`} · {x.next?.change || x.next?.hypothesis}</p>)}</div>
        <div className="card"><h4>Kept with the organization</h4><p className="note">What this campaign learned from real results is carried into the organization's future campaigns.</p></div>
      </aside>
    </div>
  );
}
