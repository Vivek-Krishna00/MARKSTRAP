import { api, C } from '../api.js';
import { METRICS } from '../copy.js';
import { Act, Empty, Loading, Section, pad, toast, useLoad, when } from '../ui.jsx';

export default function Launch({ cid, c, reload: reloadCampaign }) {
  const q = useLoad(() => api.get(`${C(cid)}/launch`), [cid]);
  if (!q.data) return <Loading err={q.err} />;
  const L = q.data;
  const reload = async () => { await q.reload(); reloadCampaign(); };
  const unready = L.items.filter(i => i.reel && !i.reel.approved);
  return (
    <div className="cols">
      <div>
        <h2>Ready to <em className="s">go live.</em></h2>
        <p className="lead">Publish each piece yourself on its platform. MarkStrap never posts anything for you. People land on <b>{L.destination || 'your destination page'}</b>.</p>
        {L.items.length ? L.items.map((it, i) => (
          <section key={it.id} className="card" style={{ marginBottom: 18 }}>
            <div className="row between"><span className="tag ice">{pad(i + 1)} · {it.platform} · {it.format}</span><span className="note mono">{it.id}</span></div>
            <h3 style={{ marginTop: 12 }}>{it.name}</h3>
            <Section>Caption</Section>
            <div className="copy">{it.headline}{'\n\n'}{it.caption}</div>
            <button className="line tiny" style={{ marginTop: 10 }} onClick={() => { navigator.clipboard.writeText(`${it.headline}\n\n${it.caption}`); toast('Caption copied'); }}>Copy caption</button>
            <Section>Posting instructions</Section>
            <dl className="kv">
              <dt>Platform</dt><dd>{it.platform}</dd><dt>Format</dt><dd>{it.format}</dd>
              <dt>When</dt><dd>{it.post_time || 'When your audience is most active'}</dd>
              <dt>Link or action</dt><dd>{L.destination || '—'}</dd>
            </dl>
            <Section>Final assets</Section>
            <div className="stack">
              {it.reel ? (it.reel.approved && it.reel.final
                ? <p style={{ margin: 0 }}>Reel <span className="tag good">approved</span> <a href={`/campaigns/${cid}/reels/${it.reel.id}/final.mp4`} download>Download MP4</a></p>
                : <p style={{ margin: 0 }}>Reel <span className="tag warn">not approved yet</span> <a href={`#/campaigns/${cid}/reels/${it.reel.id}`}>Finish it</a></p>)
                : <p className="note" style={{ margin: 0 }}>No Reel for this concept.</p>}
              {it.image ? <p style={{ margin: 0 }}>Image <a href={`/renders/${it.id}.png`} download>Download</a></p> : <p className="note" style={{ margin: 0 }}>No generated image. Visual direction: {it.visual}</p>}
            </div>
            {it.check_before_posting.length > 0 && <div className="card warn tight" style={{ marginTop: 14 }}><b>Check before posting</b>
              <ul className="clean">{it.check_before_posting.map((x, j) => <li key={j}>{x}</li>)}</ul></div>}
          </section>
        )) : <Empty>Approve a concept first. <a href={`#/campaigns/${cid}/concepts`}>Go to concepts</a></Empty>}

        {L.items.length > 0 && <>
          <Section>Measurement plan</Section>
          <div className="card">
            <p style={{ marginTop: 0 }}>Objective: <b>{L.measure.objective}</b>. Success: {L.measure.success || 'not set in the brief'}.</p>
            <p className="note">For this objective, these numbers matter most:</p>
            <div className="tags">{L.measure.metrics.map(m => <span key={m} className="tag ice">{METRICS[m] || m}</span>)}</div>
            <p className="note">Collect them from each platform's insights after a few days. The first hours count extra, so note early engagement too.</p>
            <div className="actions" style={{ marginTop: 12 }}><a className="line" href={`${C(cid)}/launch.csv`}>Download the results template</a></div>
          </div>

          <Section>Published?</Section>
          <div className={`card ${c.published_at ? 'ice' : ''}`}>
            {c.published_at ? <>
              <p style={{ marginTop: 0 }}>You marked this campaign as published on <b>{when(c.published_at)}</b>.</p>
              <div className="row"><a className="btn" href={`#/campaigns/${cid}/results`}>Add the real results</a>
                <Act className="line tiny" run={async () => { await api.post(`${C(cid)}/published`, { published: false }); await reload(); }}>Not published yet</Act></div>
            </> : <>
              <p style={{ marginTop: 0 }}>When you have posted the approved pieces yourself, mark the campaign as published so we can remind you to bring back the results.</p>
              {unready.length > 0 && <p className="note">{unready.length} Reel{unready.length > 1 ? 's are' : ' is'} not approved yet.</p>}
              <Act className="btn" run={async () => { await api.post(`${C(cid)}/published`, { published: true }); await reload(); }}>I've published it</Act>
            </>}
          </div>
        </>}
      </div>
      <aside>
        <div className="card"><h4>Campaign requirements</h4>
          <dl className="kv" style={{ gridTemplateColumns: '1fr' }}>{Object.entries(L.requirements).filter(([, v]) => v).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          {!Object.values(L.requirements).some(Boolean) && <p className="note">No restrictions recorded.</p>}</div>
      </aside>
    </div>
  );
}
