import {useEffect,useState} from 'react';
import {Activity,ArrowRight,BookOpen,ChartCandlestick,ChevronRight,CircleHelp,Compass,GraduationCap,LineChart,ShieldCheck,Target,Wallet} from 'lucide-react';
import {api,money,signed} from '../api';
import type {Instrument,LearningData,MarketState} from '../types';
import learningContent from '../data/learning.json';
import './HomeDashboard.css';

type HomePage='terminal'|'investing'|'learn'|'positions'|'report';
type Props={state:MarketState;accountId:string;displayName:string;onNavigate:(page:HomePage)=>void;onOpenChart:(symbol:string)=>void;onOpenGuide:()=>void};

function label(instrument:Instrument){return instrument.display_symbol||instrument.trading_symbol||instrument.symbol;}

function Sparkline({history,positive}:{history:{value:number}[];positive:boolean}){
  const values=history.slice(-32).map(point=>point.value).filter(value=>Number.isFinite(value));
  if(values.length<2)return <span className="home-spark-empty">Chart starts with new demo ticks</span>;
  const low=Math.min(...values);const span=Math.max(0.01,Math.max(...values)-low);
  const points=values.map((value,index)=>`${(index/(values.length-1)*100).toFixed(1)},${(38-(value-low)/span*30).toFixed(1)}`).join(' ');
  return <svg className={positive?'home-spark up':'home-spark down'} viewBox="0 0 100 44" preserveAspectRatio="none" role="img" aria-label="Recent simulated price movement"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/></svg>;
}

export default function HomeDashboard({state,accountId,displayName,onNavigate,onOpenChart,onOpenGuide}:Props){
  const [learning,setLearning]=useState<LearningData|null>(null);
  useEffect(()=>{let active=true;api<LearningData>('/api/learning').then(value=>{if(active)setLearning(value)}).catch(()=>{if(active)setLearning(null)});return()=>{active=false};},[accountId]);
  const firstName=displayName.trim().split(/\s+/)[0]||'there';
  const lessons=learningContent.lessons;
  const completed=learning?.completed.length??0;
  const nextLesson=lessons.find(lesson=>!learning?.completed.includes(lesson.id))||lessons[0];
  const indices=state.instruments.filter(item=>item.kind==='INDEX').slice(0,2);
  const featured=[...state.instruments.filter(item=>item.kind==='EQUITY').slice(0,4),...state.instruments.filter(item=>item.kind==='OPTION').slice(0,1)];
  const marginTotal=Math.max(0,state.account.available_margin+state.account.used_margin);
  const marginPct=marginTotal>0?Math.min(100,Math.max(0,state.account.used_margin/marginTotal*100)):0;
  const updated=new Date(state.updated_at);

  return <div className="home-root">
    <section className="home-heading"><div><span className="home-overline"><Compass size={15}/> YOUR PRACTICE SPACE</span><h1>Good to see you, {firstName}.</h1><p>Explore the market, test an idea and learn from each paper trade.</p></div><div className="home-mode"><span className="home-mode-dot"/> Simulated market <small>{Number.isNaN(updated.getTime())?'':`Updated ${updated.toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit'})} IST`}</small></div></section>

    <div className="home-top-grid">
      <section className="home-capital home-card" aria-label="Virtual account overview"><div className="home-card-top"><span className="home-overline"><Wallet size={16}/> YOUR PAPER ACCOUNT</span><span className="home-tag">VIRTUAL FUNDS</span></div><div className="home-capital-main"><div><span className="home-field-label">Account value</span><strong>{money(state.account.equity)}</strong><span className="home-capital-hint">Cash plus marked positions in your practice account</span></div><div className="home-capital-orb" aria-hidden="true"><ChartCandlestick size={43}/></div></div><div className="home-capital-stats"><div><span>Available margin</span><b>{money(state.account.available_margin)}</b></div><div><span>Margin in use</span><b>{money(state.account.used_margin)}</b></div><div className="home-margin-track" role="progressbar" aria-valuenow={Math.round(marginPct)} aria-valuemin={0} aria-valuemax={100} aria-label="Percentage of paper margin in use"><span style={{width:`${marginPct}%`}}/></div></div><div className="home-result-grid"><div><span>Open P&L</span><b className={state.account.unrealized_pnl<0?'home-loss':'home-gain'}>{money(state.account.unrealized_pnl)}</b><small>{state.positions.length} open position{state.positions.length===1?'':'s'}</small></div><div><span>Booked P&L</span><b className={state.account.realized_pnl<0?'home-loss':'home-gain'}>{money(state.account.realized_pnl)}</b><small>From completed trades</small></div></div><div className="home-card-actions"><button className="home-primary" onClick={()=>onNavigate('terminal')}><ChartCandlestick size={18}/> Open trading desk <ArrowRight size={17}/></button><button className="home-secondary" onClick={()=>onNavigate('positions')}>View positions <ChevronRight size={17}/></button></div></section>

      <section className="home-learning home-card" aria-label="Learning progress"><div className="home-card-top"><span className="home-overline"><GraduationCap size={17}/> KEEP LEARNING</span><span className="home-tag muted">AT YOUR PACE</span></div><div className="home-learning-main"><div className="home-learning-icon"><BookOpen size={28}/></div><div><span className="home-field-label">Your next lesson</span><h2>{nextLesson.title}</h2><p>Understand one idea, then try it with virtual money.</p></div></div><div className="home-learning-path" aria-label="Learning approach"><div><span>01</span><b>Learn an idea</b></div><div><span>02</span><b>Try it on paper</b></div><div><span>03</span><b>Review the result</b></div></div><div className="home-progress"><div><span>Lessons completed</span><b>{learning?`${completed} / ${lessons.length}`:'—'}</b></div><div className="home-progress-track" role="progressbar" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={lessons.length} aria-label="Lessons completed"><span style={{width:`${completed/Math.max(1,lessons.length)*100}%`}}/></div></div><button className="home-learning-link" onClick={()=>onNavigate('learn')}>Continue learning <ArrowRight size={17}/></button><div className="home-learning-foot"><Target size={16}/><span>Practise concepts in the F&O lab and review what changed after each trade.</span></div></section>
    </div>

    <div className="home-lower-grid"><div className="home-lower-main"><section className="home-section home-pulse" aria-label="Simulated market pulse"><div className="home-section-head"><div><span className="home-overline"><Activity size={16}/> MARKET PULSE</span><h2>Watch the practice market</h2></div><span className="home-tag">SIMULATED QUOTES</span></div><div className="home-pulse-grid">{indices.length?indices.map(item=><button key={item.symbol} className="home-pulse-tile" onClick={()=>onOpenChart(item.symbol)}><div><span>{label(item)}</span><small>{item.name}</small></div><div className="home-pulse-price"><b>{money(item.ltp)}</b><span className={item.change_pct<0?'home-loss':'home-gain'}>{signed(item.change_pct)}</span></div><Sparkline history={state.history[item.symbol]||[]} positive={item.change_pct>=0}/></button>):<p className="home-empty">Index quotes will appear when the simulator has instruments.</p>}</div><p className="home-section-note"><CircleHelp size={14}/> These prices and changes are generated for practice. They are not exchange quotes.</p></section>

      <section className="home-section home-discover" aria-label="Instruments on your practice desk"><div className="home-section-head"><div><span className="home-overline"><LineChart size={16}/> EXPLORE</span><h2>On your practice desk</h2></div><button className="home-text-link" onClick={()=>onNavigate('terminal')}>View all <ArrowRight size={16}/></button></div><div className="home-discover-list">{featured.length?featured.map(item=><button className="home-instrument" key={item.symbol} onClick={()=>onOpenChart(item.symbol)}><span className="home-instrument-avatar">{label(item).slice(0,2)}</span><span className="home-instrument-name"><b>{label(item)}</b><small>{item.name}</small></span><span className="home-instrument-price"><b>{money(item.ltp)}</b><small className={item.change_pct<0?'home-loss':'home-gain'}>{signed(item.change_pct)}</small></span><span className="home-instrument-action">Open chart <ArrowRight size={15}/></span></button>):<p className="home-empty">Search for a stock above to start exploring.</p>}</div></section></div>

      <aside className="home-aside"><section className="home-section home-next"><span className="home-overline"><ShieldCheck size={16}/> A GOOD FIRST STEP</span><h2>Plan before you place a paper order.</h2><p>Choose a share or option, write down why you would enter, and decide what would make you exit.</p><button className="home-outline-button" onClick={onOpenGuide}>Start guided practice <ArrowRight size={17}/></button></section><section className="home-section home-review"><span className="home-overline"><Activity size={16}/> LEARN FROM RESULTS</span><h2>Review the decision, not just the number.</h2><p>Your report shows price movement, quantities and charges in simple English.</p><button className="home-text-link" onClick={()=>onNavigate('report')}>Open trade report <ArrowRight size={16}/></button></section><section className="home-disclosure"><ShieldCheck size={18}/><span>All funds, prices and orders in Paperlane are simulated. No broker order is placed.</span></section></aside></div>
  </div>;
}
