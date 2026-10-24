import { useState } from 'react';
import { api, C } from '../api.js';
import { go } from '../router.js';
import { Act, Empty, Err, Eyebrow, Loading, Section, toast, useLoad } from '../ui.jsx';

function Item({ k, cid, caps, reload }) {
  const [err, setErr] = useState('');
  const c = k.content;
  const reel = k.reel;
  return (
    <section className="card" style={{ marginBottom: 18 }}>
      <div className="row between"><div><div className="kicker">{c.concept_name || 'Concept'}</div><h3 style={{ marginTop: 4 }}>{c.headline}</h3></div>
        <div className="tags"><span className="tag ice">{c.platform}</span><span className="tag">{c.format}</span></div></div>
      <Section>Caption</Section>
      <div className="copy">{c.headline}{'\n\n'}{c.body}</div>
      <button className="line tiny" style={{ marginTop: 10 }} onClick={() => { navigator.clipboard.writeText(`${c.headline}\n\n${c.body}`); toast('Caption copied'); }}>Copy caption</button>

      <div className="grid two" style={{ marginTop: 6 }}>
        <div>
          <Section>Reel</Section>
          {reel ? <div className="stack">
            <p style={{ margin: 0 }}>Status: <b>{reel.status}</b>{k.reelApproved ? <span className="tag good" style={{ marginLeft: 8 }}>final approved</span> : ''}</p>
            <a className="btn tiny" href={`#/campaigns/${cid}/reels/${reel.id}`}>Open the Reel</a>
          </div> : <div className="stack">
            <p className="note" style={{ margin: 0 }}>A 9:16 video for Reels, TikTok or Shorts, planned scene by scene. Nothing is generated until you approve the storyboard.</p>
            <Act className="btn tiny" busy="Preparing the brief…" onError={setErr} run={async () => {
              const r = await api.post(`${C(cid)}/concepts/${k.id}/reel`); go(`/campaigns/${cid}/reels/${r.id}`);
            }}>Create a Reel</Act>
          </div>}
        </div>
        <div>
          <Section>Image</Section>
          {k.image ? <img src={`/renders/${k.id}.png?v=${Date.now() >> 16}`} alt={`Image for ${c.headline}`} style={{ maxWidth: '100%', borderRadius: 10, border: '1px solid var(--rule2)' }} />
            : caps.providers.image ? <Act className="line tiny" busy="Generating…" onError={setErr} run={async () => { await api.post(`${C(cid)}/concepts/${k.id}/image`); await reload(); }}>Generate the image</Act>
              : <p className="note" style={{ margin: 0 }}>Image generation isn't connected yet. Hand the visual direction below to your designer, or use the Reel with your own photos.</p>}
        </div>
      </div>
      <Section>Visual direction for your designer</Section>
      <div className="visual">{c.visual}{c.font ? `\nTYPE — ${c.font}` : ''}</div>
      <Err>{err}</Err>
    </section>
  );
}

export default function Assets({ cid, c, reload: reloadCampaign }) {
  const q = useLoad(() => Promise.all([api.get(`${C(cid)}/concepts`), api.get('/api/capabilities')]), [cid]);
  if (!q.data) return <Loading err={q.err} />;
  const [d, caps] = q.data;
  const approved = d.concepts.filter(k => k.decision === 'approved').map(k => ({ ...k, reelApproved: k.reel && c.reel_approvals[k.reel.id] }));
  const reload = async () => { await q.reload(); reloadCampaign(); };
  return (
    <div className="cols">
      <div>
        <Eyebrow>Step 3 · Assets</Eyebrow>
        <h2>From approved idea to <em className="s">finished asset.</em></h2>
        <p className="lead">Each approved concept becomes a caption, a visual brief and, if you want one, a Reel. Edit any scene without starting over.</p>
        {approved.length ? approved.map(k => <Item key={k.id} k={k} cid={cid} caps={caps} reload={reload} />)
          : <Empty>Approve a concept first. <a href={`#/campaigns/${cid}/concepts`}>Go to concepts</a></Empty>}
        {approved.length > 0 && <div className="actions"><a className="btn" href={`#/campaigns/${cid}/launch`}>Prepare the launch pack</a></div>}
      </div>
      <aside>
        <div className="card warn"><h4>Before production starts</h4>
          <ul className="clean">{caps.notes.map((n, i) => <li key={i} className="note">{n}</li>)}</ul></div>
        <div className="card"><h4>Open source only</h4><p className="note">Every model and tool used to make assets is open source and runs on infrastructure you control.</p></div>
      </aside>
    </div>
  );
}
