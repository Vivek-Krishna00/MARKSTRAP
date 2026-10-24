import { ThemeToggle, Toaster } from './ui.jsx';
import { useRoute } from './router.js';
import { PRINCIPLE } from './copy.js';
import Home from './pages/Home.jsx';
import { OrgList, OrgNew } from './pages/Orgs.jsx';
import Org from './pages/Org.jsx';
import Product from './pages/Product.jsx';
import CampaignNew from './pages/CampaignNew.jsx';
import Campaign from './pages/Campaign.jsx';

function Page({ route }) {
  const [a, b, c, d] = route.parts;
  if (!a) return <Home />;
  if (a === 'orgs' && !b) return <OrgList />;
  if (a === 'orgs' && b === 'new') return <OrgNew />;
  if (a === 'orgs' && c === 'products' && d) return <Product oid={b} pid={d} />;
  if (a === 'orgs') return <Org oid={b} tab={c || 'profile'} />;
  if (a === 'campaigns' && b === 'new') return <CampaignNew org={route.query.org} product={route.query.product} />;
  if (a === 'campaigns' && b) return <Campaign cid={b} step={c} sub={d} />;
  return <div className="page"><h1>Not found</h1><a href="#/">Go home</a></div>;
}

export default function App() {
  const route = useRoute();
  const area = route.parts[0] || 'home';
  return (
    <>
      <header className="top">
        <a className="wordmark" href="/" aria-label="MarkStrap website"><img src="/favicon.png" alt="" width="28" height="28" /><span>MARK<b>STRAP</b></span></a>
        <nav aria-label="App">
          <a href="#/" className={area === 'home' ? 'on' : ''}>Home</a>
          <a href="#/orgs" className={area === 'orgs' || area === 'campaigns' ? 'on' : ''}>Organizations</a>
        </nav>
        <ThemeToggle />
      </header>
      <main key={route.parts.slice(0, 2).join('/')} className="fade"><Page route={route} /></main>
      <footer className="foot">
        <span>© MarkStrap</span><span className="muted">{PRINCIPLE}</span>
        <a href="/">Website</a><a href="/console" title="For specialists: the creative engine underneath a campaign">Advanced: engine console</a>
        <span style={{ marginLeft: 'auto' }}>Built on open-source models</span>
      </footer>
      <Toaster />
    </>
  );
}
