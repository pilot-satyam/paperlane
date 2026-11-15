import {lazy,Suspense,useCallback,useEffect,useRef,useState} from 'react';
import {Activity,ArrowRight,BookOpen,ChartCandlestick,ClipboardList,History,LayoutDashboard,Menu,ShieldCheck,Sparkles,TrendingUp,Wallet,X} from 'lucide-react';
import {ApiError,api,money,setAuthCsrfToken} from './api';
import type {ClosedTrade,MarketState} from './types';
import TradingDesk from './components/TradingDesk';
import ProfileMenu from './components/ProfileMenu';
import HeaderStockSearch from './components/HeaderStockSearch';
import HomeDashboard from './components/HomeDashboard';
const Learning=lazy(()=>import('./components/Learning'));
const TradeActivity=lazy(()=>import('./components/Activity'));
const InvestingDashboard=lazy(()=>import('./components/InvestingDashboard'));

type Page='home'|'terminal'|'investing'|'learn'|'positions'|'orders'|'trades'|'report'|'journal';
type Identity={id:string;display_name:string;subject:string};
type AuthResponse={authenticated:boolean;user:Identity;csrf_token:string};
const pageFromHash=():Page=>{
  const hash=window.location.hash.slice(1);
  if(hash==='activity')return 'positions';
  if(hash==='order-ticket')return 'terminal';
  return ['home','terminal','investing','learn','positions','orders','trades','report','journal'].includes(hash)?hash as Page:'home';
};
const navigation:{id:Page;label:string;icon:typeof Activity}[]=[
  {id:'home',label:'Home',icon:LayoutDashboard},
  {id:'terminal',label:'Trade',icon:ChartCandlestick},
  {id:'investing',label:'Investing',icon:TrendingUp},
  {id:'learn',label:'Learn',icon:BookOpen},
  {id:'positions',label:'Positions',icon:Wallet},
  {id:'orders',label:'Orders',icon:ClipboardList},
  {id:'trades',label:'History',icon:History},
  {id:'report',label:'Report',icon:Activity},
  {id:'journal',label:'Journal',icon:Sparkles}
];
const guideSteps=[
  {title:'Choose a share',text:'A share is a small part of a company. Start with a company you recognise. Check its name and exchange before choosing it.',page:'terminal' as Page},
  {title:'Read the quote',text:'Bid is the price offered by a buyer. Ask is the price requested by a seller. The gap between them is the spread.',page:'terminal' as Page},
  {title:'Plan an order',text:'Write down why you might enter, what would make you leave, and how much you plan to risk. Check side, quantity and charges before you place a paper order.',page:'terminal' as Page},
  {title:'Watch your position',text:'A filled paper order appears in Positions. Its open profit or loss changes with the simulated price. A pending order appears in Orders.',page:'positions' as Page},
  {title:'Review the result',text:'After you close a position, the report explains the price move and charges. Compare what happened with your original plan.',page:'report' as Page}
];
const guideKey='paperlane.react.guide.v1';
const signedInBeforeKey='paperlane.auth.signed-in-before.v1';
const resumedThisTabKey='paperlane.auth.resume-attempted.v1';
const rememberSignIn=()=>{try{localStorage.setItem(signedInBeforeKey,'1');sessionStorage.removeItem(resumedThisTabKey);}catch{/* Storage can be unavailable in private browsing. */}};
const forgetSignIn=()=>{try{localStorage.removeItem(signedInBeforeKey);sessionStorage.removeItem(resumedThisTabKey);}catch{/* The server session is still revoked. */}};
const resumeExistingSignIn=()=>{if(window.location.protocol!=='https:')return false;try{if(localStorage.getItem(signedInBeforeKey)==='1'&&sessionStorage.getItem(resumedThisTabKey)!=='1'){sessionStorage.setItem(resumedThisTabKey,'1');window.location.assign('/auth/login');return true;}}catch{/* Fall back to the sign-in screen. */}return false;};

function mergeHistory(previous:MarketState['history'], delta:MarketState['history']):MarketState['history']{
  const merged={...previous};
  for(const [symbol,points] of Object.entries(delta)){
    const old=merged[symbol]||[];
    const lastTime=old.at(-1)?.time;
    const fresh=lastTime?points.filter(point=>point.time>lastTime):points;
    if(fresh.length)merged[symbol]=[...old,...fresh].slice(-1800);
  }
  return merged;
}

export default function App(){
  const [identity,setIdentity]=useState<Identity|null|undefined>(undefined);
  const [signInFailed,setSignInFailed]=useState(()=>new URLSearchParams(window.location.search).get('auth_error')==='signin');
  const [state,setState]=useState<MarketState|null>(null);
  const [page,setPage]=useState<Page>(pageFromHash);
  const [learningTrack,setLearningTrack]=useState<'all'|'investing'>('all');
  const [learningLessonId,setLearningLessonId]=useState<string|null>(null);
  const [selected,setSelected]=useState('NIFTY');
  const [error,setError]=useState('');
  const [toast,setToast]=useState('');
  const [menuOpen,setMenuOpen]=useState(false);
  const [guideOpen,setGuideOpen]=useState(false);
  const [guideStep,setGuideStep]=useState(()=>{const value=Number(localStorage.getItem(guideKey));return Number.isInteger(value)&&value>=0&&value<guideSteps.length?value:0;});
  const [exitOrder,setExitOrder]=useState<{symbol:string;side:'BUY'|'SELL';quantity:number}|null>(null);
  const [replay,setReplay]=useState<ClosedTrade|null>(null);
  const mounted=useRef(true);
  const toastTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const stateSnapshot=useRef<MarketState|null>(null);
  const historyCursor=useRef<string|null>(null);
  const refreshRequest=useRef(0);
  const appliedRequest=useRef(0);

  const showToast=useCallback((message:string)=>{setToast(message);if(toastTimer.current)clearTimeout(toastTimer.current);toastTimer.current=setTimeout(()=>setToast(''),5500);},[]);
  const refresh=useCallback(async()=>{const requestId=++refreshRequest.current;try{const cursor=historyCursor.current;const data=await api<MarketState>(cursor?`/api/state?history_after=${encodeURIComponent(cursor)}`:'/api/state');if(!mounted.current||requestId<appliedRequest.current)return;appliedRequest.current=requestId;const previous=stateSnapshot.current;const next=data.history_mode==='delta'&&previous?{...data,history:mergeHistory(previous.history,data.history)}:data;stateSnapshot.current=next;historyCursor.current=data.history_cursor||null;setState(next);setError('');setSelected(old=>data.instruments.some(i=>i.symbol===old)?old:data.instruments[0]?.symbol||'NIFTY');}catch(e){if(!mounted.current||requestId<appliedRequest.current)return;if(e instanceof ApiError&&e.status===401){setAuthCsrfToken('');stateSnapshot.current=null;historyCursor.current=null;if(resumeExistingSignIn())return;setIdentity(null);setState(null);}else setError(e instanceof Error?e.message:'The simulator is unavailable.');}},[]);
  useEffect(()=>{mounted.current=true;const check=async()=>{try{const response=await fetch('/api/auth/me',{credentials:'same-origin',signal:AbortSignal.timeout(10000)});if(!mounted.current)return;if(!response.ok){if(response.status===401&&resumeExistingSignIn())return;setIdentity(null);return;}const data=await response.json() as AuthResponse;rememberSignIn();setAuthCsrfToken(data.csrf_token);setSignInFailed(false);if(new URLSearchParams(window.location.search).has('auth_error'))window.history.replaceState(null,'',window.location.pathname+window.location.hash);setIdentity(data.user);}catch{if(mounted.current)setIdentity(null);}};void check();return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(!identity)return;mounted.current=true;let timer:ReturnType<typeof setTimeout>;let active=true;const poll=async()=>{await refresh();if(active)timer=setTimeout(poll,2000);};void poll();return()=>{active=false;clearTimeout(timer);if(toastTimer.current)clearTimeout(toastTimer.current);};},[refresh,identity?.id]);
  useEffect(()=>{const update=()=>setPage(pageFromHash());window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[]);
  const navigate=useCallback((next:Page)=>{setPage(next);window.location.hash=next;setMenuOpen(false);window.scrollTo({top:0,behavior:'smooth'});},[]);
  const openChart=useCallback((symbol:string)=>{setSelected(symbol);setExitOrder(null);setReplay(null);navigate('terminal');},[navigate]);
  const prepareExit=(symbol:string)=>{const position=state?.positions.find(p=>p.symbol===symbol);if(!position)return;setSelected(symbol);setExitOrder({symbol,side:position.quantity>0?'SELL':'BUY',quantity:Math.abs(position.quantity)});navigate('terminal');showToast('Exit prepared. Check the quantity and submit the paper order yourself.');};
  const showReplay=(trade:ClosedTrade)=>{setSelected(trade.symbol);setReplay(trade);navigate('terminal');showToast('Chart shows saved entry and exit markers when that history is available.');};
  const nextGuide=()=>{if(guideStep===guideSteps.length-1){setGuideOpen(false);localStorage.removeItem(guideKey);setGuideStep(0);}else{const next=guideStep+1;setGuideStep(next);localStorage.setItem(guideKey,String(next));}};
  const connected=!!state&&state.market_status==='DEMO SESSION'&&Date.now()-new Date(state.updated_at).getTime()<10000;
  const signOut=async()=>{try{await api<{ok:boolean}>('/api/auth/logout',{});forgetSignIn();setAuthCsrfToken('');appliedRequest.current=++refreshRequest.current;stateSnapshot.current=null;historyCursor.current=null;setState(null);setIdentity(null);}catch(e){showToast(e instanceof Error?e.message:'Could not sign out.');}};
  const currentPage=page==='home'?<HomeDashboard state={state!} accountId={identity?.id||''} displayName={identity?.display_name||''} onNavigate={navigate} onOpenChart={openChart} onOpenGuide={()=>setGuideOpen(true)}/>:
    page==='terminal'?<TradingDesk state={state!} accountId={identity?.id||''} selected={selected} onSelect={setSelected} onUpdate={refresh} showToast={showToast} exitOrder={exitOrder} replay={replay}/>:
    page==='investing'?<InvestingDashboard state={state!} accountId={identity?.id||''} onOpenChart={openChart} onLearn={lessonId=>{setLearningTrack('investing');setLearningLessonId(lessonId??null);navigate('learn')}}/>:
    page==='learn'?<Learning state={state!} initialTrack={learningTrack} initialLessonId={learningLessonId} onNavigate={next=>navigate(next as Page)} showToast={showToast}/>:
    <TradeActivity state={state!} section={page} onRefresh={refresh} onPrepareExit={prepareExit} onReplayTrade={showReplay} showToast={showToast} onSelect={openChart}/>;
  if(identity===undefined)return <div className="app-shell"><main className="app-main"><div className="loading-card"><span className="loading-orb"/> Checking your sign-in…</div></main></div>;
  if(identity===null)return <div className="app-shell auth-shell"><main className="auth-main"><div className="auth-card"><div className="brand auth-brand"><span className="brand-icon">p</span><span>paperlane<small>MARKET LAB</small></span></div><p className="eyebrow">YOUR PRIVATE PRACTICE ACCOUNT</p><h1>Learn trading and investing at your pace.</h1><p>Sign in to keep your paper trades, lessons and notes in your own account. All prices and orders remain simulated.</p>{signInFailed&&<p role="alert" className="auth-error">That sign-in did not finish. Please start again here in the same browser tab.</p>}<a className="auth-sign-in" href="/auth/login">{signInFailed?'Try signing in again':'Continue with Google or email'} <ArrowRight size={18}/></a></div></main></div>;
  return <div className={`app-shell page-${page}`}>
    <header className="app-header"><div className="header-inner"><button className="brand" onClick={()=>navigate('home')} aria-label="Paperlane home"><span className="brand-icon">p</span><span>paperlane<small>MARKET LAB</small></span></button><HeaderStockSearch instruments={state?.instruments||[]} onOpenChart={openChart} onRefresh={refresh}/><nav className={menuOpen?'app-nav open':'app-nav'} aria-label="Main navigation">{navigation.map(item=>{const Icon=item.icon;return <button key={item.id} className={page===item.id?'active':''} onClick={()=>{if(item.id==='learn')setLearningTrack('all');navigate(item.id)}} aria-current={page===item.id?'page':undefined}><Icon size={16}/>{item.label}</button>;})}</nav><div className="header-actions"><span className="demo-pill"><span className="status-dot"/> SIMULATED MARKET</span><ProfileMenu identity={identity} onNavigate={destination=>{if(destination==='learn')setLearningTrack('all');navigate(destination)}} onOpenGuide={()=>setGuideOpen(true)} onSignOut={()=>void signOut()}/><button className="mobile-menu" onClick={()=>setMenuOpen(!menuOpen)} aria-label={menuOpen?'Close menu':'Open menu'}>{menuOpen?<X size={20}/>:<Menu size={20}/>}</button></div></div></header>
    <main className="app-main">
      {page!=='home'&&<section className="hero"><div><p className="eyebrow"><span className="eyebrow-line"/> PAPERLANE / LEARN BY DOING</p><h1>{page==='terminal'?'Your practice trading desk.':page==='investing'?'Invest with a clear process.':page==='learn'?'Learn it. Then try it.':page==='report'?'Understand every trade.':page==='journal'?'Keep your thinking clear.':'Your practice, in view.'}</h1><p>{page==='terminal'?'Explore synthetic prices, plan an order and learn from the result.':page==='investing'?'Study companies, compare practice holdings and learn how to make long-term decisions.':'Every step is part of your market education. Take your time and learn from what happened.'}</p></div><div className="hero-actions"><button className="guide-button" onClick={()=>setGuideOpen(true)}><Sparkles size={17}/> New here? Start guided practice <ArrowRight size={16}/></button><span className={connected?'connection good':'connection'}><span className="status-dot"/>{connected?'Demo connected':error?'Simulator offline':'Updating prices'}</span></div></section>}
      {error&&<div className="app-error" role="status">Connection issue: {error}. Your saved records remain on this computer. <button onClick={()=>void refresh()}>Retry</button></div>}
      {state&&<>{page!=='investing'&&page!=='home'&&<section className="metric-grid" aria-label="Paper account summary"><Metric label="Account value" value={money(state.account.equity)} detail="Virtual balance" icon={<Wallet size={19}/>}/><Metric label="Available margin" value={money(state.account.available_margin)} detail={`${money(state.account.used_margin)} in use`} icon={<ShieldCheck size={19}/>}/><Metric label="Open P&L" value={money(state.account.unrealized_pnl)} detail={`${state.positions.length} open positions`} icon={<Activity size={19}/>} tone={state.account.unrealized_pnl}/><Metric label="Booked P&L" value={money(state.account.realized_pnl)} detail="After completed fills" icon={<ChartCandlestick size={19}/>} tone={state.account.realized_pnl}/></section>}<Suspense fallback={<div className="loading-card"><span className="loading-orb"/> Opening workspace…</div>}>{currentPage}</Suspense></>}
      {!state&&!error&&<div className="loading-card"><span className="loading-orb"/> Connecting to your paper trading account…</div>}
    </main>
    <footer className="app-footer"><span>paperlane <b>·</b> Practice with purpose.</span><span>Synthetic prices · Virtual money · No real orders</span></footer>
    {toast&&<div className="app-toast" role="status">{toast}</div>}
    {guideOpen&&<div className="guide-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setGuideOpen(false)}}><section className="guide-panel" role="dialog" aria-modal="true" aria-labelledby="guide-title"><div className="guide-head"><span>YOUR FIRST PAPER TRADE</span><button onClick={()=>setGuideOpen(false)} aria-label="Close guide"><X size={18}/></button></div><div className="guide-progress"><span>STEP {guideStep+1} OF {guideSteps.length}</span><div>{guideSteps.map((_,index)=><i key={index} className={index<=guideStep?'done':''}/>)}</div></div><div className="guide-illustration"><BookOpen size={36}/><span>Learn one decision at a time</span></div><h2 id="guide-title">{guideSteps[guideStep].title}</h2><p>{guideSteps[guideStep].text}</p><div className="guide-panel-actions"><button onClick={()=>{navigate(guideSteps[guideStep].page);setGuideOpen(false)}}>Open {guideSteps[guideStep].page==='terminal'?'terminal':guideSteps[guideStep].page}</button><button className="primary" onClick={nextGuide}>{guideStep===guideSteps.length-1?'Finish guide':'Next step'} <ArrowRight size={16}/></button></div><small>The guide never submits an order. You control each paper trade.</small></section></div>}
  </div>;
}

function Metric({label,value,detail,icon,tone}:{label:string;value:string;detail:string;icon:React.ReactNode;tone?:number}){return <article className="metric-card"><div className="metric-label"><span>{label}</span>{icon}</div><strong className={tone===undefined?'':tone<0?'loss':'gain'}>{value}</strong><small>{detail}</small></article>}
