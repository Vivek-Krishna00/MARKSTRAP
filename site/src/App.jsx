import { useEffect, useRef, useState } from 'react';
import BlurText from './reactbits/BlurText.jsx';
import AnimatedContent from './reactbits/AnimatedContent.jsx';
import CountUp from './reactbits/CountUp.jsx';
import { DitherPhoto, Hands, Orb, ParticleGrid } from './ascii.jsx';

const REDUCED = typeof window !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

/* React Bits, configured once for the whole site. Under reduced motion the content renders static. */
const Title = ({ text, className = 'h1', as: Tag = 'h2', delay = 60 }) =>
  REDUCED ? <Tag className={className}>{text}</Tag>
    : <Tag className={className} aria-label={text}><BlurText text={text} delay={delay} stepDuration={0.4} blur={10} distance={18} className="blur" /></Tag>;
const Reveal = ({ children, delay = 0, className = '' }) =>
  REDUCED ? <div className={className}>{children}</div>
    : <AnimatedContent distance={28} duration={0.9} ease="power3.out" blur={6} delay={delay} className={className}>{children}</AnimatedContent>;
const Num = ({ to, suffix = '' }) => REDUCED ? <>{to}{suffix}</> : <CountUp to={to} suffix={suffix} duration={1.6} />;

const SOURCES = [
  { id: 'adobe', label: 'Adobe, "Demand for content will grow 5x by 2027", survey of 1,600+ marketers, 16 June 2025', url: 'https://business.adobe.com/blog/71-percent-of-marketers-say-content-demand-to-increase-5x' },
  { id: 'nielsen', label: 'Nielsen, 2025 Annual Marketing Report', url: 'https://www.nielsen.com/insights/2025/annual-marketing-report-2025-chaos-to-clarity/' },
  { id: 'nielsen-iab', label: 'Nielsen findings summarised by Nielsen EMEA for IAB Europe, 2025', url: 'https://iabeurope.eu/guest-member-blog-post-navigating-uncertainty-insights-from-nielsens-2025-annual-marketing-report/' },
  { id: 'ipip', label: 'IPIP-NEO-120 personality dataset (simulated audience is sampled from a model fitted on 271,547 respondents)', url: 'https://osf.io/tbmh5/' },
];

const pad = n => String(n).padStart(2, '0');
const NAV = [['how', 'How it works'], ['evidence', 'Why now'], ['compare', 'Before & after'], ['architecture', 'Architecture']];

const systemLight = () => matchMedia('(prefers-color-scheme: light)').matches;

function ThemeToggle() {
  const [light, setLight] = useState(() => (document.documentElement.dataset.theme || (systemLight() ? 'light' : 'dark')) === 'light');
  useEffect(() => {
    const t = light ? 'light' : 'dark';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('ms-theme', t); } catch { /* storage blocked: theme still applies for this visit */ }
  }, [light]);
  return <button className="theme" onClick={() => setLight(l => !l)} aria-label="Switch colour theme">{light ? '◑ Dark' : '◐ Light'}</button>;
}

export default function App() {
  const headRef = useRef(null);
  return (
    <>
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="MarkStrap home"><img className="mark" src="/favicon.png" alt="" width="28" height="28" /><span>MARK<b>STRAP</b></span></a>
        <nav className="site-nav" aria-label="Main">
          {NAV.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
        </nav>
        <ThemeToggle />
        <a className="cta" href="/app">Open the app</a>
      </header>

      <main>
        <Problem headRef={headRef} />
        <Evidence />
        <Cost />
        <Meet />
        <div id="how">
          <Bring />
          <ExploreProduce />
          <LaunchLearn />
        </div>
        <Compare />
        <Architecture />
        <Closing />
      </main>

      <footer className="site-footer">
        <div className="foot-top">
          <a className="wordmark" href="/"><img className="mark" src="/favicon.png" alt="" width="28" height="28" /><span>MARK<b>STRAP</b></span></a>
          <nav aria-label="Footer">
            <a href="/app">Open the app</a>
            {NAV.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
            <a href="/console">Engine console</a>
          </nav>
        </div>
        <div className="foot-sources">
          <span className="label">Sources</span>
          <ol>{SOURCES.map(x => <li key={x.id}><a href={x.url} target="_blank" rel="noreferrer">{x.label}</a></li>)}</ol>
        </div>
        <p className="note">Simulated results help shortlist ideas; they are not predictions of demand. Before/after rows describe intended improvements, not measured results.</p>
      </footer>
    </>
  );
}

const Scene = ({ id, children, className = '' }) => <section className={`scene ${className}`} id={id}>{children}</section>;
const Kicker = ({ children }) => <div className="kicker"><span className="label">{children}</span></div>;

/* 01 */
function Problem({ headRef }) {
  return (
    <Scene id="problem" className="hero">
      <Hands paused={false} clearRef={headRef} />
      <div className="hero-center" ref={headRef}>
        <h1 className="display" aria-label="How many good ideas never get a fair test?">
          {REDUCED ? <>How many good ideas<br />never get a <em className="s">fair test?</em></> : <>
            <BlurText text="How many good ideas" delay={70} stepDuration={0.45} distance={16} className="blur line" />
            <span className="line-row">
              <BlurText text="never get a" delay={70} stepDuration={0.45} distance={16} className="blur" />
              <em className="s"><BlurText text="fair test?" delay={90} stepDuration={0.5} distance={16} className="blur" /></em>
            </span>
          </>}
        </h1>
        <Reveal delay={0.6}><p className="hero-copy">The insight is there. The ambition is there.<br />Every new campaign experiment still has a production cost.</p></Reveal>
      </div>
      <div className="persona">
        <span className="label">The person we build for · illustrative</span>
        <p>Marketing lead at a coaching centre. Knows the students, the parents and the exam calendar. Has one designer, one ad budget and more good ideas than slots to test them.</p>
      </div>
      <div className="scroll-cue" aria-hidden="true"><span className="label">Scroll</span><i /></div>
    </Scene>
  );
}

/* 02 */
function Evidence() {
  const stats = [
    { n: 71, s: '%', t: <>of marketers expect demand for content to grow <em className="s">five-fold or more</em> by 2027.</>, src: 'Adobe, 2025 · 1,600+ marketers', url: SOURCES[0].url },
    { n: 56, s: '%', t: <>say their biggest social challenge is <em className="s">knowing what will resonate</em> on each platform.</>, src: 'Adobe, 2025', url: SOURCES[0].url },
    { n: 54, s: '%', t: <>plan to <em className="s">tighten budgets</em> this year. Only 32% measure spend across digital and traditional comprehensively.</>, src: 'Nielsen Annual Marketing Report, 2025', url: SOURCES[2].url },
  ];
  return (
    <Scene id="evidence">
      <div className="wrap">
        <Kicker n={2}>Evidence</Kicker>
        <Title text="More content, less certainty, tighter budgets." />
        <div className="stats">
          {stats.map((x, i) => (
            <Reveal key={i} delay={0.15 * i} className="stat">
              <div className="stat-n"><Num to={x.n} suffix={x.s} /></div>
              <p>{x.t}</p>
              <a className="src" href={x.url} target="_blank" rel="noreferrer">{x.src} ↗</a>
            </Reveal>
          ))}
        </div>
      </div>
    </Scene>
  );
}

/* 03 */
function Cost() {
  const aud = ['Class 11 students', 'Parents', 'Repeat aspirants'];
  const msg = ['Results', 'Faculty', 'Fees', 'Batch timing'];
  const fmt = ['Reel', 'Carousel', 'Search ad'];
  return (
    <Scene id="cost">
      <div className="wrap">
        <Kicker n={3}>Cost of learning</Kicker>
        <Title text="A modest test is already 36 pieces of work." />
        <Reveal className="matrix-eq">
          <span><b><Num to={3} /></b> audiences</span><i>×</i><span><b><Num to={4} /></b> messages</span><i>×</i><span><b><Num to={3} /></b> formats</span><i>=</i><span className="ice"><b><Num to={36} /></b> variations</span>
        </Reveal>
        <Reveal delay={0.2} className="matrix">
          {aud.map((a, ai) => (
            <div key={a} className="m-group">
              <div className="label">{a}</div>
              <div className="m-grid">
                {msg.map(m => fmt.map(f => <span key={m + f} title={`${a} · ${m} · ${f}`} className="cell" style={{ animationDelay: `${(ai * 12) * 0.03}s` }} />))}
              </div>
              <div className="m-axis"><span>{msg.length} messages × {fmt.length} formats</span></div>
            </div>
          ))}
        </Reveal>
        <Reveal delay={0.35}>
          <p className="aside">If each variation needed ~3 hours of copy, design and setup, that is <b className="mono">~108 hours</b> before a single real result. <span className="tag">Illustrative assumption</span></p>
        </Reveal>
      </div>
    </Scene>
  );
}

/* 04 */
function Meet() {
  const cycle = ['Understand', 'Explore', 'Evaluate', 'Produce', 'Approve', 'Launch', 'Measure', 'Improve'];
  return (
    <Scene id="meet">
      <div className="wrap meet">
        <div>
          <Kicker n={4}>Meet MarkStrap</Kicker>
          <h2 className="h1">{REDUCED ? 'Your direction.' : <BlurText text="Your direction." delay={70} className="blur" />}<br /><em className="s">A continuous campaign engine.</em></h2>
          <Reveal delay={0.3}><p className="lead">An AI marketing agency that explores campaign possibilities, produces the selected assets, runs approved experiments and turns real responses into the next step. You set the direction and approve what goes out.</p></Reveal>
        </div>
        <Reveal delay={0.2} className="orbit">
          <Orb paused={false} size={260} />
          {cycle.map((c, i) => {
            const a = (i / cycle.length) * Math.PI * 2 - Math.PI / 2;
            return <span key={c} className="orbit-label" style={{ left: `${50 + Math.cos(a) * 47}%`, top: `${50 + Math.sin(a) * 47}%` }}><i>{pad(i + 1)}</i>{c}</span>;
          })}
          <svg className="orbit-ring" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="40" /></svg>
        </Reveal>
      </div>
    </Scene>
  );
}

/* 05 */
function Bring() {
  return (
    <Scene id="bring">
      <div className="wrap">
        <Kicker n={5}>Bring</Kicker>
        <Title text="Hand over what you already have." />
        <div className="bring">
          <Reveal className="stack">
            <div className="doc doc-1"><span className="label">Brochure · PDF</span><p className="doc-title">JEE & NEET Foundation, 2026 batches</p><div className="lines"><i /><i /><i style={{ width: '70%' }} /><i /><i style={{ width: '55%' }} /></div></div>
            <div className="doc doc-2"><span className="label">Photography · 24 images</span><DitherPhoto seed={2} /></div>
            <div className="doc doc-3"><span className="label">Brand material</span>
              <div className="swatches"><i style={{ background: '#16324F' }} /><i style={{ background: '#F2B134' }} /><i style={{ background: '#F0F1ED' }} /></div>
              <p className="type-sample">Aa — Poppins</p><p className="mono small">Never promise ranks</p></div>
          </Reveal>
          <div className="arrow" aria-hidden="true">→</div>
          <Reveal delay={0.25} className="brief">
            <div className="label">Extracted campaign brief</div>
            <dl>
              <dt>Offering</dt><dd>Two-year JEE foundation course, evening batches</dd>
              <dt>Audience</dt><dd>Class 10 students and their parents, within 8 km</dd>
              <dt>Objective</dt><dd><span className="ice">Enrollment</span> · locked for the campaign</dd>
              <dt>Messages</dt><dd>Small batches · faculty who answer doubts · transparent fees</dd>
              <dt>Constraints</dt><dd>English + Hindi · no rank guarantees · ₹60,000</dd>
              <dt>Destination</dt><dd>Admissions page with batch timings</dd>
              <dt>Missing</dt><dd className="q">Is there a scholarship test this year?</dd>
            </dl>
          </Reveal>
        </div>
        <p className="aside">A tourism board brings visitor guides and footage; a founder with an unbuilt idea brings a description and prototype screens. The same brief comes out.</p>
      </div>
    </Scene>
  );
}

/* 06 */
function ExploreProduce() {
  const hyp = ['Parents respond to doubt-solving, not toppers', 'Students respond to batch-size comparisons', 'Evening timing is the hook for school students', 'Fee transparency beats discounts', 'Alumni stories outperform faculty profiles'];
  const short = ['“Ask the doubt. Get the answer the same evening.”', '“30 students. Not 300.”', '“Fees on one page. No surprises.”'];
  const formats = ['Reel', 'Carousel', 'Search ad', 'WhatsApp post', 'Admissions page'];
  return (
    <Scene id="explore">
      <div className="wrap">
        <Kicker n={6}>Explore and produce</Kicker>
        <Title text="Explore widely. Produce only what earned it." />
        <Reveal className="flow">
          <div className="col"><div className="label">Hypotheses · many</div>{hyp.map((h, i) => <p key={h} className="hyp"><i>H{i + 1}</i>{h}</p>)}<p className="hyp dim"><i>…</i>dozens more, cheaply</p></div>
          <div className="col center"><div className="label">Agent evaluation</div>
            <div className="evalbox"><p>Specialist makers draft concepts</p><p>A simulated audience, sampled from real personality data, reacts</p><p>Critique explains <em className="s">why</em></p><p className="note">Shortlists. Never proves demand.</p></div></div>
          <div className="col"><div className="label">Creative shortlist</div>{short.map(s => <p key={s} className="short">{s}</p>)}
            <div className="label" style={{ marginTop: 28 }}>Produced across formats</div>
            <div className="formats">{formats.map(f => <span key={f}>{f}</span>)}</div></div>
          <svg className="flow-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {[18, 30, 42, 54, 66].map(y => <path key={y} d={`M31 ${y} C 36 ${y}, 36 50, 40 50`} />)}
            {[30, 42, 54].map(y => <path key={'o' + y} d={`M62 50 C 66 50, 66 ${y}, 69 ${y}`} />)}
          </svg>
        </Reveal>
      </div>
    </Scene>
  );
}

/* 07 */
function LaunchLearn() {
  const nodes = [['Approved distribution', 'You publish approved pieces on the right platforms'], ['Audience responses', 'Real clicks, saves, inquiries, enrollments'], ['Evaluation', 'Scored against this campaign’s own baseline'], ['Next experiment', 'A specific hypothesis, change and success metric']];
  return (
    <Scene id="launch">
      <div className="wrap">
        <Kicker n={7}>Launch and learn</Kicker>
        <Title text="Real responses decide what happens next." />
        <Reveal className="loop">
          <svg className="loop-ring" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><ellipse cx="50" cy="50" rx="36" ry="36" vectorEffect="non-scaling-stroke" /></svg>
          {nodes.map(([t, d], i) => <div key={t} className={`loop-node n${i}`}><span className="mono ice">{pad(i + 1)} {['↘', '↙', '↖', '↗'][i]}</span><b>{t}</b><p>{d}</p></div>)}
          <div className="loop-core"><span className="label">Shared memory</span><p>Every result is kept: what worked, what didn't, and why.</p></div>
        </Reveal>
        <Reveal delay={0.3} className="same">
          <span className="label">Same workflow</span>
          <span><b>Coaching centre</b> → admissions page</span>
          <span><b>Tourism board</b> → official trip-planning page</span>
          <span><b>Unbuilt idea</b> → transparent early-access page</span>
        </Reveal>
        <p className="aside">A weak campaign alone isn't treated as proof that an offering has no market.</p>
      </div>
    </Scene>
  );
}

/* 08 */
function Compare() {
  const rows = [
    ['Develop and produce each selected concept before testing', 'Explore alternatives before committing to full production'],
    ['Coordinate audience and platform variations separately', 'Coordinated variations from one shared campaign brief'],
    ['Review results, then prepare another brief', 'Evaluation connects directly to the next proposed experiment'],
    ['Gather past findings across reports and accounts', 'Reuse shared campaign memory'],
    ['Repeatable execution consumes specialist capacity', 'Repeatable work automated; human direction retained'],
  ];
  const metrics = ['Time from brief to live experiment', 'Total cost per experiment', 'Time from results to the next experiment', 'Useful experiments within a fixed budget', 'Creative quality and qualified campaign outcomes'];
  return (
    <Scene id="compare">
      <div className="wrap">
        <Kicker n={8}>Before and after</Kicker>
        <Title text="Same expertise. More of it tested." />
        <Reveal className="compare">
          <div className="c-head"><span className="label">Today</span><span className="label ice">With MarkStrap · intended</span></div>
          {rows.map(([a, b], i) => <div key={i} className="c-row"><span className="mono idx">{pad(i + 1)}</span><p>{a}</p><p className="b">{b}</p></div>)}
        </Reveal>
        <Reveal delay={0.2} className="metrics">
          <span className="label">Pilot metrics</span>
          <ol>{metrics.map(m => <li key={m}>{m}</li>)}</ol>
          <p className="note">Proposed improvements, not measured results.</p>
        </Reveal>
      </div>
    </Scene>
  );
}

/* 09 */
function Architecture() {
  const agents = [['Research', 'market and audience context'], ['Strategy', 'audiences, positioning, offers'], ['Creative', 'competing maker agents'], ['Simulation', 'audience from real personality data'], ['Critique', 'per-part reasons'], ['Production', 'final assets for the shortlist'], ['Evaluation', 'real results to next experiment']];
  return (
    <Scene id="architecture">
      <div className="wrap">
        <Kicker n={9}>Architecture · proposed</Kicker>
        <Title text="Specialists, one shared memory." />
        <Reveal className="arch">
          <svg className="arch-lines" viewBox="0 0 100 100" aria-hidden="true">
            {agents.map((_, i) => { const a = (i / agents.length) * Math.PI * 2 - Math.PI / 2; return <line key={i} x1="50" y1="50" x2={50 + Math.cos(a) * 40} y2={50 + Math.sin(a) * 40} />; })}
            <circle cx="50" cy="50" r="40" />
          </svg>
          <div className="arch-core"><span className="label ice">Shared campaign memory</span><p>Brief · constraints · decisions · experiment history</p></div>
          {agents.map(([n, d], i) => {
            const a = (i / agents.length) * Math.PI * 2 - Math.PI / 2;
            return <div key={n} className="arch-node" style={{ left: `${50 + Math.cos(a) * 40}%`, top: `${50 + Math.sin(a) * 40}%` }}><b>{n}</b><span>{d}</span></div>;
          })}
        </Reveal>
        <p className="aside">Open models served through an OpenAI-compatible API · memory on Graphiti + FalkorDB · audience personas sampled from the IPIP-NEO-120 dataset.</p>
      </div>
    </Scene>
  );
}

/* 10 */
function Closing() {
  return (
    <Scene id="close" className="closing">
      <ParticleGrid paused={false} />
      <div className="close-center">
        <h2 className="display" aria-label="Give more ideas a fair test.">{REDUCED ? <>Give more ideas a <em className="s">fair test.</em></> : <span className="line-row"><BlurText text="Give more ideas a" delay={70} className="blur" /><em className="s"><BlurText text="fair test." delay={90} className="blur" /></em></span>}</h2>
        <Reveal delay={0.5}><div className="wordmark big">MARK<b>STRAP</b></div></Reveal>
        <Reveal delay={0.8}><a className="quiet" href="/app">Open the app →</a></Reveal>
      </div>
    </Scene>
  );
}
