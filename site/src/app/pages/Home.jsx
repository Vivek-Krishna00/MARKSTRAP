import { api } from '../api.js';
import { Empty, Eyebrow, Loading, Section, useLoad, when } from '../ui.jsx';
import { Orb } from '../../ascii.jsx';

const FLOW = ['Organization', 'Products', 'Campaigns', 'Concepts', 'Approved assets', 'Real results', 'Next experiment'];

function CampaignRow({ c }) {
  return (
    <a className="todo" href={`#/campaigns/${c.id}/${c.where}`}>
      <span className="tag ice">{c.stage}</span>
      <span><b>{c.name}</b><small>{c.org}{c.product ? ` · ${c.product}` : ''} · updated {when(c.updated)}</small></span>
      <span className="note">Open →</span>
    </a>
  );
}

function Group({ title, rows, empty }) {
  return (
    <div className="card">
      <div className="row between"><h4>{title}</h4><span className="count">{rows.length}</span></div>
      {rows.length ? rows.slice(0, 4).map(c => <p key={c.id} style={{ margin: '8px 0 0' }}><a href={`#/campaigns/${c.id}/${c.where}`}>{c.name}</a> <span className="note">· {c.org}</span></p>)
        : <p className="note" style={{ margin: '6px 0 0' }}>{empty}</p>}
    </div>
  );
}

export default function Home() {
  const { data: h, err } = useLoad(() => api.get('/api/home'), [], { poll: 5000, active: true });
  if (!h) return <Loading err={err} />;
  const active = h.campaigns.filter(c => c.index < 8);
  if (!h.orgs.length) {
    return (
      <div className="page">
        <div className="hero">
          <div>
            <Eyebrow>Your marketing agency</Eyebrow>
            <h1>Start with the <em className="s">organization.</em></h1>
            <p className="lead">Tell us who you are once. We research your business, keep what you approve, and reuse it for every product and campaign. Ideas are tested on a simulated audience first; real results decide what works.</p>
            <div className="actions"><a className="btn" href="#/orgs/new">Create an organization</a></div>
          </div>
          <Orb size={260} />
        </div>
        <Section>How it fits together</Section>
        <div className="cycle">{FLOW.map((s, i) => <span key={s} className={i === 0 ? 'on' : ''}>{i + 1}. {s}</span>)}</div>
      </div>
    );
  }
  return (
    <div className="page">
      <div className="hero">
        <div>
          <Eyebrow>Home</Eyebrow>
          <h1>What needs <em className="s">you</em> today.</h1>
          <p className="lead" style={{ marginBottom: 0 }}>{h.attention.length ? `${h.attention.length} thing${h.attention.length > 1 ? 's' : ''} waiting for your decision.` : 'Nothing is waiting for you. Everything in progress is moving.'}</p>
        </div>
        <Orb size={190} />
      </div>
      <div className="grid three" style={{ margin: '22px 0' }}>
        <div className="card stat"><b>{h.orgs.length}</b><span>organizations</span></div>
        <div className="card stat"><b>{active.length}</b><span>active campaigns</span></div>
        <div className="card stat"><b>{h.waiting.length}</b><span>waiting for real results</span></div>
      </div>

      <Section count={h.attention.length}>Needs your attention</Section>
      {h.attention.length ? h.attention.map((t, i) => (
        <a key={i} className="todo" href={t.href}>
          <span className="dot" aria-hidden="true" />
          <span><b>{t.text}</b><small>{t.org}{t.campaign ? ` · ${t.campaign}` : ''}</small></span>
          <span className="note">Open →</span>
        </a>
      )) : <Empty art={' \\o/ \n  |  \n / \\ '}>All caught up.</Empty>}

      <div className="grid auto" style={{ marginTop: 26 }}>
        <Group title="Briefs to confirm" rows={h.briefs} empty="None waiting." />
        <Group title="Concepts to approve" rows={h.concepts} empty="None waiting." />
        <Group title="Assets being prepared" rows={h.assets} empty="Nothing in production." />
        <Group title="Waiting for results" rows={h.waiting} empty="Nothing live right now." />
        <Group title="Recently completed" rows={h.done} empty="Nothing finished yet." />
      </div>

      <Section count={active.length}>Active campaigns</Section>
      {active.length ? active.map(c => <CampaignRow key={c.id} c={c} />) : <Empty>No campaigns yet. Open an organization to start one.</Empty>}

      <Section count={h.orgs.length}>Organizations</Section>
      <div className="grid auto">
        {h.orgs.map(o => (
          <a key={o.id} className="card tile" href={`#/orgs/${o.id}`}>
            <h3>{o.name}</h3>
            <p className="note" style={{ margin: 0 }}>{o.products} product{o.products === 1 ? '' : 's'} · {o.campaigns} campaign{o.campaigns === 1 ? '' : 's'}</p>
            {(o.pending_findings > 0 || o.draft_products > 0) && <div className="tags" style={{ marginTop: 10 }}>
              {o.pending_findings > 0 && <span className="tag warn">{o.pending_findings} findings to review</span>}
              {o.draft_products > 0 && <span className="tag warn">{o.draft_products} products to approve</span>}
            </div>}
          </a>
        ))}
        <a className="card tile" href="#/orgs/new" style={{ borderStyle: 'dashed' }}><h3>＋ New organization</h3><p className="note" style={{ margin: 0 }}>Add a client or brand</p></a>
      </div>
    </div>
  );
}
