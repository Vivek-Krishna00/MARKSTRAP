import { api } from '../api.js';
import { Icon } from '../icons.jsx';
import { Loading, useLoad, when } from '../ui.jsx';

const FLOW = ['Organization', 'Products', 'Campaign', 'Concepts', 'Assets', 'Results', 'Next experiment'];
const PIPELINE = [
  ['briefs', 'Briefs', 'Confirm the campaign brief'],
  ['concepts', 'Concepts', 'Choose a creative direction'],
  ['assets', 'Production', 'Prepare approved assets'],
  ['waiting', 'Live', 'Collect real results'],
  ['done', 'Learned', 'Choose the next experiment'],
];
const n = (k, one, many = `${one}s`) => `${k} ${k === 1 ? one : many}`;

function Metric({ value, label, note, tone = '' }) {
  return <div className={`dash-metric ${tone}`}><strong>{String(value).padStart(2, '0')}</strong><div><span>{label}</span><small>{note}</small></div></div>;
}

function CampaignRow({ c }) {
  return (
    <a className="campaign-row" href={`#/campaigns/${c.id}/${c.where}`}>
      <span className="campaign-mark" aria-hidden="true"><i /></span>
      <span className="campaign-name"><b>{c.name}</b><small>{c.org}{c.product ? ` / ${c.product}` : ''}</small></span>
      <span className="campaign-stage">{c.stage}</span>
      <span className="campaign-date">Updated {when(c.updated)}</span>
      <Icon name="arrow" size={15} />
    </a>
  );
}

export default function Home() {
  const { data: h, err } = useLoad(() => api.get('/api/home'), [], { poll: 5000, active: true });
  if (!h) return <Loading err={err} />;
  const active = h.campaigns.filter(c => c.index < 8);
  const firstOrg = h.orgs[0];

  if (!h.orgs.length) {
    return (
      <div className="page home-dashboard home-empty">
        <div className="empty-start">
          <span className="overline">New workspace</span>
          <h1>Start with the organization.<br /><em>Keep the learning.</em></h1>
          <p>Give MarkStrap the context once. It becomes the source for products, campaigns and every experiment that follows.</p>
          <a className="btn" href="#/orgs/new"><Icon name="plus" size={16} /> Create an organization</a>
        </div>
        <ol className="home-flow">{FLOW.map((s, i) => <li key={s}><span>{String(i + 1).padStart(2, '0')}</span>{s}</li>)}</ol>
      </div>
    );
  }

  return (
    <div className="page home-dashboard">
      <header className="dash-head">
        <div>
          <span className="overline">Workspace overview</span>
          <h1>Campaign control.</h1>
          <p>{h.attention.length ? `${n(h.attention.length, 'decision')} needs you.` : 'Nothing is waiting for you.'} Pick up where the work needs judgment.</p>
        </div>
        <div className="dash-actions">
          <a className="line" href="#/orgs/new"><Icon name="plus" size={15} /> Organization</a>
          <a className="btn" href={`#/campaigns/new?org=${firstOrg.id}`}>New campaign <span aria-hidden="true">↗</span></a>
        </div>
      </header>

      <section className="dash-metrics" aria-label="Workspace summary">
        <Metric value={h.attention.length} label="Needs attention" note="Decisions waiting for you" tone={h.attention.length ? 'hot' : ''} />
        <Metric value={active.length} label="Active campaigns" note="Currently moving" />
        <Metric value={h.waiting.length} label="Awaiting results" note="Live in the market" />
        <Metric value={h.orgs.length} label="Organizations" note={`${n(h.orgs.reduce((a, o) => a + o.products, 0), 'product')} in the library`} />
      </section>

      <div className="dash-grid">
        <div className="dash-main">
          <section className="dash-panel attention-panel">
            <header className="panel-title"><div><span>01</span><h2>Inbox</h2></div><small>{h.attention.length ? 'Your judgment is required' : 'No decisions waiting'}</small></header>
            {h.attention.length ? <div className="attention-list">{h.attention.map((t, i) => (
              <a className="attention-task" href={t.href} key={`${t.href}-${i}`}>
                <span className="task-signal" aria-hidden="true" />
                <span><b>{t.text}</b><small>{[t.org, t.campaign].filter(Boolean).join(' / ')}</small></span>
                <span className="task-kind">{t.kind || 'Review'}</span>
                <span className="task-open">Review <Icon name="arrow" size={14} /></span>
              </a>
            ))}</div> : <div className="inbox-clear"><span>✓</span><p><b>You’re caught up.</b><small>New approvals and review requests will appear here.</small></p></div>}
          </section>

          <section className="dash-panel pipeline-panel">
            <header className="panel-title"><div><span>02</span><h2>Campaign pipeline</h2></div><small>{n(h.campaigns.length, 'campaign')} across all stages</small></header>
            <div className="pipeline-board">
              {PIPELINE.map(([key, title, empty]) => (
                <div className={`pipeline-column${h[key].length ? ' has-work' : ''}`} key={key}>
                  <div className="pipeline-title"><span>{title}</span><b>{h[key].length}</b></div>
                  <div className="pipeline-items">
                    {h[key].slice(0, 4).map(c => <a key={c.id} href={`#/campaigns/${c.id}/${c.where}`}><b>{c.name}</b><small>{c.org}</small><Icon name="arrow" size={13} /></a>)}
                    {!h[key].length && <p>{empty}</p>}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="dash-panel campaigns-panel">
            <header className="panel-title"><div><span>03</span><h2>Recent campaigns</h2></div><small>Most recently updated</small></header>
            <div className="campaign-table">
              {h.campaigns.length ? h.campaigns.slice(0, 6).map(c => <CampaignRow c={c} key={c.id} />)
                : <div className="table-empty"><p>No campaigns yet.</p><a href={`#/campaigns/new?org=${firstOrg.id}`}>Create the first campaign →</a></div>}
            </div>
          </section>
        </div>

        <aside className="dash-side">
          <section className="org-panel">
            <header><div><span>04</span><h2>Organizations</h2></div><a href="#/orgs">View all</a></header>
            <div className="org-cards">
              {h.orgs.map(o => (
                <a className={`org-summary${o.pending_findings > 0 ? ' has-review' : ''}`} href={`#/orgs/${o.id}`} key={o.id}>
                  <span className="org-monogram">{o.name.slice(0, 2).toUpperCase()}</span>
                  <span className="org-summary-name"><b>{o.name}</b><small>{n(o.products, 'product')} / {n(o.campaigns, 'campaign')}</small></span>
                  {o.pending_findings > 0
                    ? <span className="org-summary-review"><b>Profile</b><span>Review</span><Icon name="arrow" size={14} /></span>
                    : <Icon name="arrow" size={14} />}
                </a>
              ))}
            </div>
            <a className="add-org" href="#/orgs/new"><Icon name="plus" size={14} /> Add organization</a>
          </section>

          <section className="work-model">
            <span className="overline">How work moves</span>
            <ol>{FLOW.map((s, i) => <li className={i < 3 ? 'ready' : ''} key={s}><span>{String(i + 1).padStart(2, '0')}</span><i />{s}</li>)}</ol>
            <p>Simulation filters ideas. Your approvals control what ships. Real results shape what happens next.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
