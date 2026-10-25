import { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { api, C } from '../api.js';
import { ASSET_TYPES, CRITERIA, REEL_STAGES, ROLES } from '../copy.js';
import { Act, Empty, Err, Loading, Section, pad, toast, useLoad } from '../ui.jsx';

const PLATFORMS = [['instagram_reels', 'Instagram Reels'], ['tiktok', 'TikTok'], ['youtube_shorts', 'YouTube Shorts']];
const SPEAKERS = [['auto', 'Auto (from the voice style)'], ['af_heart', 'Heart · warm female (US)'], ['af_bella', 'Bella · bright female (US)'],
  ['am_michael', 'Michael · male (US)'], ['am_fenrir', 'Fenrir · deep male (US)'], ['bf_emma', 'Emma · female (UK)'],
  ['bm_george', 'George · male (UK)'], ['hf_alpha', 'Alpha · female (Hindi)'], ['hm_omega', 'Omega · male (Hindi)']];
const pct = x => `${Math.round(x * 100)}%`;
const IMG = /\.(png|jpe?g|webp|gif)$/i;

/* An input that saves when you leave it. */
function Saved({ label, value, onSave, area, type = 'text', disabled, placeholder, rows = 2 }) {
  const [v, setV] = useState(value ?? '');
  useEffect(() => { setV(value ?? ''); }, [value]);
  const id = `r-${label.replace(/\W+/g, '-').toLowerCase()}`;
  const props = { id, value: v, disabled, placeholder, onChange: e => setV(e.target.value), onBlur: () => String(v) !== String(value ?? '') && onSave(v) };
  return <div><label className="f" htmlFor={id}>{label}</label>{area ? <textarea rows={rows} {...props} /> : <input type={type} {...props} />}</div>;
}

function Choice({ label, value, options, onSave, disabled }) {
  const id = `r-${label.replace(/\W+/g, '-').toLowerCase()}`;
  return <div><label className="f" htmlFor={id}>{label}</label>
    <select id={id} value={value} disabled={disabled} onChange={e => onSave(e.target.value)}>{options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>;
}

function Scene({ s, i, R, base, put, act, images, busy }) {
  const st = s.state || {}, a = st.asset || {};
  const status = busy && st.status === 'running' ? 'making' : st.status || 'pending';
  const file = useRef(null);
  return (
    <article className={`scene ${st.status === 'failed' ? 'failed' : ''}`} aria-label={`Scene ${i + 1}`}>
      <div className="thumb">{a.path && a.kind === 'image' ? <img src={`/campaigns/${R.cid}/reels/${R.id}/${s.id}?v=${a.hash || ''}`} alt={`Scene ${i + 1}`} /> : <span>{a.kind === 'video' ? 'video' : 'motion'}</span>}</div>
      <div>
        <div className="tags"><span className="tag ice">{pad(i + 1)} · {s.purpose}</span><span className="tag">{s.startSeconds}–{s.endSeconds}s</span>
          <span className={`tag ${status === 'done' ? 'good' : status === 'failed' ? 'bad' : status === 'making' ? 'ice pulse' : ''}`}>{status}</span>
          {a.fallback && <span className="tag warn" title={a.fallback}>stand-in</span>}</div>
        <Saved label="Voiceover" area value={s.voiceover} disabled={busy} onSave={v => put(s.id, { voiceover: v })} />
        <div className="fields">
          <Saved label="On-screen text" value={s.onScreenText} disabled={busy} onSave={v => put(s.id, { onScreenText: v })} />
          <Choice label="Visual source" value={s.assetType} disabled={busy} options={Object.entries(ASSET_TYPES)} onSave={v => put(s.id, { assetType: v })} />
        </div>
        <Saved label="What we see" area value={s.visualDescription} disabled={busy} onSave={v => put(s.id, { visualDescription: v })} />
        {images.length > 0 && <><label className="f">References in this scene</label>
          <div className="row">{images.map(x => (
            <label key={x.id} className="chk"><input type="checkbox" disabled={busy} checked={s.referenceAssetIds.includes(x.id)}
              onChange={e => put(s.id, { referenceAssetIds: e.target.checked ? [...s.referenceAssetIds, x.id] : s.referenceAssetIds.filter(y => y !== x.id) })} />{x.name}</label>
          ))}</div></>}
        <details><summary>Generation prompt</summary><pre className="visual" style={{ marginTop: 8 }}>{s.generationPrompt}</pre></details>
        {st.error ? <div className="err">{st.error}. A motion-graphics stand-in is used; make a new take or use your own media.</div>
          : a.fallback && s.assetType !== 'motion_graphics' ? <p className="note">Stand-in used: {a.fallback}</p> : null}
        {R.renders?.preview && <div className="row" style={{ marginTop: 12 }}>
          <Act className="line tiny" disabled={busy} run={() => act(() => api.post(`${base}/scenes/${s.id}/regenerate`))}>New take of this scene</Act>
          <button className="line tiny" disabled={busy} onClick={() => file.current.click()}>Use my own media</button>
          <input ref={file} type="file" hidden accept="image/*,video/*" onChange={e => act(() => api.form(`${base}/scenes/${s.id}/replace`, { file: e.target.files[0] }))} />
        </div>}
      </div>
    </article>
  );
}

export default function Reel({ cid, rid, c, reload: reloadCampaign }) {
  const base = `${C(cid)}/reels/${rid}`;
  const q = useLoad(() => api.get(base), [rid], { poll: 1500, active: d => d?.busy });
  const lib = useLoad(() => api.get(`/api/orgs/${c.org.id}`), [c.org.id]);
  const [err, setErr] = useState('');
  const [role, setRole] = useState('product');
  const [note, setNote] = useState('');
  const fileRef = useRef(null);
  const R0 = q.data;
  if (!R0) return <Loading err={q.err} />;
  const R = { ...R0, cid };
  const b = R.brief, spec = R.spec, busy = R.busy;
  const act = async (fn) => { setErr(''); try { await fn(); } catch (e) { setErr(e.message); } await q.reload(); reloadCampaign(); };
  const patch = fields => act(() => api.patch(`${base}/brief`, fields));
  const put = (sid, fields) => act(() => api.put(`${base}/scenes/${sid}`, fields));
  const images = R.assets.filter(a => a.kind === 'image' || a.kind === 'video');
  const media = (lib.data?.sources || []).filter(s => s.path && (IMG.test(s.path) || /\.(mp4|mov|webm)$/i.test(s.path)));
  const r = R.renders || {}, crit = R.critic;
  const cur = R.stage || (R.status === 'done' ? 'final' : r.preview ? 'preview' : '');
  const label = ['failed', 'interrupted'].includes(R.status) ? 'Resume' : r.preview ? 'Re-assemble' : 'Produce the Reel';
  return (
    <div className="cols">
      <div>
        <a className="link back" href={`#/campaigns/${cid}/assets`}><Icon name="back" size={14} />Back to assets</a>
        <h2>From concept to <em className="s">Reel.</em></h2>
        <p className="lead">Plan every scene first, review it, then produce. Expensive generation starts only after you approve the storyboard, and edits re-make only the scenes they touch.</p>

        <Section>1 · Creative brief</Section>
        <div className="card">
          <div className="fields">
            {[['product', 'Product or service'], ['audience', 'Audience'], ['objective', 'Objective'], ['cta', 'Call to action'],
              ['brandVoice', 'Brand voice'], ['style', 'Visual style']].map(([k, l]) => <Saved key={k} label={l} value={b[k]} disabled={busy} onSave={v => patch({ [k]: v })} />)}
            <Saved label="Brand colours" value={(b.colors || []).join(' ')} placeholder="#107C10 #FFFFFF" disabled={busy} onSave={v => patch({ colors: v })} />
            <div className="fields" style={{ gap: '0 12px' }}>
              <Choice label="Platform" value={b.platform} options={PLATFORMS} disabled={busy} onSave={v => patch({ platform: v })} />
              <Saved label="Seconds" type="number" value={b.durationSeconds} disabled={busy} onSave={v => patch({ durationSeconds: v })} />
            </div>
          </div>
          <Section>Voice, captions and music</Section>
          <div className="fields">
            <Choice label="Voiceover" value={b.voice || 'on'} options={[['on', 'Spoken voiceover'], ['off', 'No voice, captions and music only']]} disabled={busy} onSave={v => patch({ voice: v })} />
            <Choice label="Captions" value={b.captions || 'on'} options={[['on', 'Word-by-word captions'], ['off', 'No captions']]} disabled={busy} onSave={v => patch({ captions: v })} />
            <Choice label="Language" value={b.language || 'English'} options={[['English', 'English'], ['Hindi', 'Hindi']]} disabled={busy} onSave={v => patch({ language: v })} />
            <Choice label="Speaker" value={b.speaker || 'auto'} options={SPEAKERS} disabled={busy || b.voice === 'off'} onSave={v => patch({ speaker: v })} />
            <Saved label="Voice style" value={b.voiceStyle} placeholder="Warm, unhurried, a little playful" disabled={busy} onSave={v => patch({ voiceStyle: v })} />
            <Saved label="Music direction" value={b.musicDirection} placeholder="Cosy lo-fi, builds at the end" disabled={busy} onSave={v => patch({ musicDirection: v })} />
          </div>
          <Saved label="Must not show or say" area value={b.mustNot} disabled={busy} onSave={v => patch({ mustNot: v })} />
          <Saved label="Notes for the director" area value={b.notes} placeholder="Anything the scenes must show or avoid" disabled={busy} onSave={v => patch({ notes: v })} />
        </div>

        <Section count={R.assets.length}>2 · References and brand material</Section>
        <div className="drop" role="button" tabIndex={0} onClick={() => fileRef.current.click()} onKeyDown={e => e.key === 'Enter' && fileRef.current.click()}>
          <pre aria-hidden="true">{' .-------.\n | ◐  ▲ |\n |  ▤   |\n \'-------\''}</pre>
          <div><div className="big">Logo, product shots, characters, reference videos, music</div>
            <div className="note">Products and characters stay consistent across every scene that uses them.</div>
            <div className="row" style={{ marginTop: 10 }} onClick={e => e.stopPropagation()}>
              <select style={{ maxWidth: 220 }} value={role} onChange={e => setRole(e.target.value)} aria-label="What is this file">{Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <input style={{ flex: 1, minWidth: 180 }} value={note} onChange={e => setNote(e.target.value)} placeholder="What must stay the same? e.g. the green logo" aria-label="What must stay the same" />
            </div></div>
          <input ref={fileRef} type="file" multiple hidden accept="image/*,video/*,audio/*,.ttf,.otf" onChange={e => act(async () => {
            for (const file of e.target.files) await api.form(`${base}/assets`, { file, role, note });
          })} />
        </div>
        {media.length > 0 && <div className="card tight" style={{ marginTop: 12 }}>
          <div className="label">From this organization's knowledge base</div>
          <div className="row" style={{ marginTop: 8 }}>{media.map(s => (
            <Act key={s.id} className="line tiny" disabled={busy} run={() => act(() => api.post(`${base}/library/${s.id}?role=${role}&note=${encodeURIComponent(note)}`))}>＋ {s.name}</Act>
          ))}</div></div>}
        <div style={{ marginTop: 12 }}>{R.assets.map(a => (
          <div key={a.id} className="item">
            <span className="k">{a.kind === 'image' ? <img src={`/campaigns/${cid}/reels/${R.id}/${a.id}`} alt="" /> : a.kind === 'video' ? <Icon name="play" /> : a.kind === 'audio' ? <Icon name="music" /> : <Icon name="type" />}</span>
            <span className="n"><b>{a.name}</b><small>{ROLES[a.role] || a.role}{a.meta?.note ? ` · ${a.meta.note}` : ''}</small></span><span className="tag">{a.id}</span>
          </div>
        ))}</div>

        <Section>{spec ? `3 · Storyboard · ${spec.scenes.length} scenes · ${spec.durationSeconds}s` : '3 · Storyboard'}</Section>
        {spec ? <>
          <div className="visual" style={{ marginBottom: 14 }}>HOOK — {spec.hook.onScreenText} · {spec.hook.visualAction}{'\n'}TONE — {spec.creativeDirection.tone} · {spec.creativeDirection.visualStyle}{'\n'}CTA — {spec.callToAction.onScreenText}</div>
          {R.scenes.map((s, i) => <Scene key={s.id} s={s} i={i} R={R} base={base} put={put} act={act} images={images} busy={busy} />)}
        </> : <Empty art={' [1][2][3]\n [4][5][6]'}>No storyboard yet. The director plans a hook, the middle beats and a call to action, timed to the second.</Empty>}
        <div className="actions" style={{ marginTop: 14 }}>
          <Act className={spec ? 'line' : 'btn'} disabled={busy} run={() => act(() => api.post(`${base}/storyboard`))}>{spec ? 'Re-plan the storyboard' : 'Plan the storyboard'}</Act>
          {spec && <span className="note">Re-planning replaces your scene edits.</span>}
        </div>

        {spec && <>
          <Section>4 · Production</Section>
          <div className="card">
            {!r.preview && <div className="card warn tight" style={{ marginBottom: 12 }}><b>What production can do right now</b>
              <ul className="clean">{R.capabilities.notes.map((n, i) => <li key={i} className="note">{n}</li>)}</ul></div>}
            <div className="cycle">{Object.entries(REEL_STAGES).map(([k, l]) => <span key={k} className={k === cur && busy ? 'on' : ''}>{l}</span>)}</div>
            <p className={`note ${busy ? 'pulse' : ''}`}>{busy ? `Working · ${REEL_STAGES[R.stage] || R.status}. You can leave this page; it keeps going.`
              : r.preview ? 'Preview ready. Edits re-make only the scenes they touch.' : 'Makes visuals, voice and captions, reviews the cut, repairs weak scenes, then renders a preview.'}</p>
            {R.error && <Err>{R.error}. Finished scenes are kept; fix the cause and press Resume.</Err>}
            <Act className="btn" disabled={busy} run={() => act(() => api.post(`${base}/produce`))}>{label}</Act>
          </div>
        </>}

        {crit && <>
          <Section>{`5 · Quality review · ${crit.overall}/10`}</Section>
          {crit.visual && <div className="visual" style={{ marginBottom: 14 }}>
            FRAMES JUDGED BY — {crit.visual.by}{crit.visual.stopScroll != null ? ` · STOP-SCROLL ${crit.visual.stopScroll}/10` : ''} · SCENE VARIETY {crit.visual.stats?.variety} · REAL IMAGERY {Math.round((crit.visual.stats?.real_imagery || 0) * 100)}%
            {crit.visual.verdict && <>{'\n'}“{crit.visual.verdict}”</>}{crit.visual.note && <>{'\n'}{crit.visual.note}</>}
          </div>}
          <div className="scores">{Object.entries(crit.scores).map(([k, v]) => (
            <div key={k} className={`score ${v < 6 ? 'low' : ''}`}><span>{CRITERIA[k] || k}</span><b>{v.toFixed(0)}</b><i style={{ '--w': `${v * 10}%` }} /></div>
          ))}</div>
          {(crit.history || []).map(h => <p key={h.round} className="note">Round {h.round}: repaired {h.repaired.join(', ')} automatically.</p>)}
          {crit.issues.length ? <ul className="clean" style={{ marginTop: 10 }}>{crit.issues.slice(0, 8).map((x, i) => <li key={i}>{x.sceneId && <span className="mono">{x.sceneId} </span>}{x.problem}{x.fix && <span className="note"> → {x.fix}</span>}</li>)}</ul>
            : <p className="note">No open issues.</p>}
          {crit.screening && <>
            <Section>{`MiroFish screening · ${crit.screening.people} people · ${Math.round(crit.screening.weight * 100)}% Llama`}</Section>
            <table className="screen"><thead><tr><th>Version</th><th>Llama</th><th>Reach</th><th>Share</th><th>Engage</th><th>Crowd</th><th>Score</th></tr></thead>
              <tbody>{crit.screening.posts.map(p => <tr key={p.post}><td>{p.post.includes('~') ? 'With fixes' : 'As rendered'}</td>
                <td className="num">{p.llama.toFixed(1)}</td><td className="num">{pct(p.reach)}</td><td className="num">{pct(p.share_rate)}</td>
                <td className="num">{pct(p.engage_rate)}</td><td className="num">{p.crowd.toFixed(1)}</td><td className="num"><b>{p.score.toFixed(1)}</b></td></tr>)}</tbody></table>
            {crit.screening.posts.flatMap(p => (p.words || []).slice(0, 2).map((w, i) => <div key={p.post + i} className="quote" style={{ marginTop: 12 }}>“{w.text}”<small>— {w.persona}, {w.age} · {p.post.includes('~') ? 'with fixes' : 'as rendered'} · {w.reaction}</small></div>))}
            <p className="note">Simulated people read Llama's description of the frames, not the pixels. "With fixes" describes an improved cut; it isn't rendered. Real results override all of this.</p>
          </>}
        </>}

        {r.preview && <>
          <Section>6 · Preview and final approval</Section>
          <div className="player">
            <video controls playsInline preload="metadata" src={`/campaigns/${cid}/reels/${R.id}/${r.final ? 'final' : 'preview'}.mp4?v=${r.preview_at || ''}${r.final ? 'f' : ''}`} />
            <div>
              <p style={{ marginTop: 0 }}>{r.final ? 'The final 1080 × 1920 export is ready.' : 'This is a quick low-resolution preview. Export renders the full 1080 × 1920 MP4.'}</p>
              <div className="actions" style={{ marginTop: 10 }}>
                <Act className={r.final ? 'line' : 'btn'} disabled={busy} run={() => act(() => api.post(`${base}/export`))}>{r.final ? 'Export again' : 'Export the final MP4'}</Act>
                {r.final && <a className="line" href={`/campaigns/${cid}/reels/${R.id}/final.mp4`} download>Download MP4</a>}
              </div>
              {r.final && <div className={`card ${R.approved ? 'ice' : 'warn'} tight`} style={{ marginTop: 16 }}>
                {R.approved ? <><b>Final approved.</b> <span className="note">It is in the launch pack.</span>
                  <div className="row" style={{ marginTop: 8 }}><Act className="line tiny" run={() => act(() => api.post(`${base}/approve`, { approved: false }))}>Withdraw approval</Act>
                    <a className="btn tiny" href={`#/campaigns/${cid}/launch`}>Go to launch</a></div></>
                  : <><b>Watch it through, then approve.</b> <p className="note">Only approved Reels go into the launch pack.</p>
                    <Act className="btn tiny" run={() => act(async () => { await api.post(`${base}/approve`, { approved: true }); toast('Reel approved'); })}>Approve the final Reel</Act></>}
              </div>}
              <p className="note">Captions stay inside the platform safe zones; music dips under the voice.</p>
            </div>
          </div>
        </>}
        <Err>{err}</Err>
      </div>
      <aside>
        <div className="card"><h4>Production tools</h4>
          {Object.entries(R.providers).map(([k, v]) => <p key={k} className="note row between" style={{ margin: '4px 0' }}><span>{k}</span><span className="mono" style={{ color: v ? 'var(--text)' : 'var(--faint)' }}>{v || 'not available'}</span></p>)}
          <p className="note">Every tool is open source. When one is missing we fall back to your uploads and motion graphics, and say so before production.</p></div>
      </aside>
    </div>
  );
}
