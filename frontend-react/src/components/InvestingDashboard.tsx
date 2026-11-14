import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, BookOpen, Building2, ChartNoAxesCombined, CircleHelp, Compass, ListChecks, Search, ShieldCheck, Wallet } from 'lucide-react';
import { api, money, signed } from '../api';
import type { Instrument, MarketState } from '../types';
import { PriceChart } from './TradingDesk';
import './InvestingDashboard.css';

type Props = {
  state: MarketState;
  accountId: string;
  onOpenChart: (symbol: string) => void;
  onLearn: (lessonId?: string) => void;
};
type InvestingOverview = {
  mode: 'SIMULATED';
  shared_account: boolean;
  summary: { holding_count: number; cost_basis: number; market_value: number; unrealized_pnl: number; return_pct: number | null };
  holdings: { symbol: string; name: string; quantity: number; average_price: number; ltp: number; cost_basis: number; market_value: number; unrealized_pnl: number; return_pct: number; allocation_pct: number }[];
};

function nameOf(instrument: Instrument) {
  return instrument.display_symbol || instrument.trading_symbol || instrument.symbol;
}

const researchSteps = [
  { id: 'business', title: 'Understand the business', tip: 'What does it sell, and how does it earn money?', lessonId: 'invest_share' },
  { id: 'reports', title: 'Read a company report', tip: 'Start with the annual report and its risk section.', lessonId: 'invest_research' },
  { id: 'numbers', title: 'Check the numbers', tip: 'Compare sales, profit, cash flow and debt over time.', lessonId: 'invest_statements' },
  { id: 'risks', title: 'Name the main risk', tip: 'What could make your reason for buying wrong?', lessonId: 'invest_multibagger' },
];

export default function InvestingDashboard({ state, accountId, onOpenChart, onLearn }: Props) {
  const equities = useMemo(() => state.instruments.filter(item => item.kind === 'EQUITY').sort((a, b) => nameOf(a).localeCompare(nameOf(b))), [state.instruments]);
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [search, setSearch] = useState('');
  const analysisRef = useRef<HTMLDivElement>(null);
  const [overview, setOverview] = useState<InvestingOverview | null>(null);
  const [overviewError, setOverviewError] = useState('');
  useEffect(() => {
    let active = true;
    const refresh = () => { api<InvestingOverview>('/api/investing/overview').then(result => { if (active) { setOverview(result); setOverviewError(''); } }).catch(error => { if (active) setOverviewError(error instanceof Error ? error.message : 'Could not load holdings.'); }); };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [accountId]);
  const selected = equities.find(item => item.symbol === selectedSymbol) || equities[0];
  const researchKey = selected ? `paperlane.invest.research.v1.${accountId}.${encodeURIComponent(selected.symbol)}` : '';
  const [researchState, setResearchState] = useState<{key: string; ids: string[]}>({ key: '', ids: [] });
  const completedResearch = researchState.key === researchKey ? researchState.ids : [];
  useEffect(() => {
    if (!researchKey) { setResearchState({ key: '', ids: [] }); return; }
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(researchKey) || '[]');
      setResearchState({ key: researchKey, ids: Array.isArray(saved) ? saved.filter((id): id is string => researchSteps.some(step => step.id === id)) : [] });
    } catch { setResearchState({ key: researchKey, ids: [] }); }
  }, [researchKey]);
  function toggleResearch(id: string) {
    if (!researchKey) return;
    const next = completedResearch.includes(id) ? completedResearch.filter(item => item !== id) : [...completedResearch, id];
    setResearchState({ key: researchKey, ids: next });
    try { localStorage.setItem(researchKey, JSON.stringify(next)); } catch { /* Browser storage may be unavailable. */ }
  }
  const holdings = overview?.holdings || [];
  const holdingsValue = overview?.summary.market_value;
  const holdingsPnl = overview?.summary.unrealized_pnl;
  const largestHolding = holdings[0];
  const topThreeAllocation = holdings.slice(0, 3).reduce((sum, holding) => sum + holding.allocation_pct, 0);
  const selectedHistory = selected ? state.history[selected.symbol] || [] : [];
  const observedPrices = selectedHistory.map(point => point.value).filter(value => Number.isFinite(value) && value > 0);
  const observedLow = observedPrices.length ? Math.min(...observedPrices) : null;
  const observedHigh = observedPrices.length ? Math.max(...observedPrices) : null;
  const filtered = equities.filter(item => `${item.symbol} ${item.display_symbol || ''} ${item.name}`.toLowerCase().includes(search.toLowerCase())).slice(0, 80);
  const showHoldingChart = (symbol: string) => {
    setSelectedSymbol(symbol);
    analysisRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return <div className="invest-root">
    <section className="invest-intro">
      <div><span className="invest-eyebrow"><Compass size={15}/> INVESTING SPACE</span><h2>Look beyond the next candle.</h2><p>Explore shares, practise researching a business, and review your virtual holdings. Use the same chart tools as the trading terminal.</p></div>
      <button type="button" onClick={() => onLearn()}><BookOpen size={17}/> Browse investing lessons <ArrowRight size={16}/></button>
    </section>

    <div className="invest-note" role="note"><ShieldCheck size={19}/><span>Prices and charts are synthetic practice data. Longer chart ranges show generated demo history, not actual past prices. There are no live financial statements or valuation ratios here.</span></div>

    <section className="invest-metrics" aria-label="Virtual equity holdings summary">
      <article><span><Wallet size={17}/> SHARE HOLDINGS</span><strong>{overview?.summary.holding_count ?? '—'}</strong><small>Long equity positions in your paper account</small></article>
      <article><span><Building2 size={17}/> PRACTICE MARKET VALUE</span><strong>{money(holdingsValue)}</strong><small>Quantity × latest synthetic price</small></article>
      <article><span><ChartNoAxesCombined size={17}/> OPEN SHARE RESULT</span><strong className={(holdingsPnl ?? 0) < 0 ? 'invest-loss' : 'invest-gain'}>{money(holdingsPnl)}</strong><small>{overview?.summary.return_pct == null ? 'No long share holdings yet' : `${overview.summary.return_pct >= 0 ? '+' : ''}${overview.summary.return_pct.toFixed(2)}% on long shares`}</small></article>
    </section>
    {overviewError && <p className="invest-api-error" role="status">Holdings are temporarily unavailable: {overviewError}</p>}

    <div className="invest-main-grid">
      <section className="invest-panel invest-watchlist" aria-label="Explore active shares">
        <div className="invest-panel-title"><div><span>EXPLORE</span><h3>Shares on your desk</h3></div><b>{equities.length} active</b></div>
        <label className="invest-search"><Search size={17}/><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Find an active share" aria-label="Find an active share"/></label>
        <div className="invest-stock-list">{filtered.map(item => <button type="button" key={item.symbol} className={item.symbol === selected?.symbol ? 'selected' : ''} onClick={() => setSelectedSymbol(item.symbol)}><span><b>{nameOf(item)}</b><small>{item.name}</small></span><span className="invest-stock-price"><b>{money(item.ltp)}</b><small className={item.change_pct < 0 ? 'invest-loss' : 'invest-gain'}>{signed(item.change_pct)} demo</small></span></button>)}{!filtered.length && <p className="invest-list-empty">No active share matches. Open the terminal to search the wider catalogue.</p>}</div>
        <p className="invest-list-note">This list contains shares already active in the simulator. It is not a stock screen or recommendation.</p>
      </section>

      <div className="invest-analysis" ref={analysisRef}>
        {selected ? <>
          <div className="invest-stock-header"><div><span>COMPANY VIEW / {selected.exchange || 'CASH'}</span><h3>{nameOf(selected)}</h3><p>{selected.name}</p></div><button type="button" onClick={() => onOpenChart(selected.symbol)}>Open in terminal <ArrowRight size={16}/></button></div>
          <div className="invest-quote-row"><div><span>SIMULATED PRICE</span><b>{money(selected.ltp)}</b></div><div><span>OBSERVED LOW</span><b>{observedLow === null ? '—' : money(observedLow)}</b></div><div><span>OBSERVED HIGH</span><b>{observedHigh === null ? '—' : money(observedHigh)}</b></div><div><span>OBSERVED TICKS</span><b>{observedPrices.length}</b></div></div>
          <PriceChart instrument={selected} history={selectedHistory} accountId={accountId} investing/>
          <p className="invest-chart-note">The quote and observed low/high above cover only simulator ticks. The 1M to 5Y chart paths are generated for practice, not real stock history. They do not affect paper orders.</p>
          <section className="invest-checklist invest-panel" aria-label={`Research checklist for ${nameOf(selected)}`}>
            <div className="invest-checklist-head"><div><span><ListChecks size={16}/> START YOUR RESEARCH</span><h3>Before buying {nameOf(selected)}</h3><p>Use this short checklist to practise looking beyond the price chart.</p></div><strong>{completedResearch.length} / {researchSteps.length} done</strong></div>
            <progress value={completedResearch.length} max={researchSteps.length} aria-label="Research steps marked complete"/>
            <div className="invest-checklist-grid">{researchSteps.map(step => <div key={step.id} className={`invest-checklist-item${completedResearch.includes(step.id) ? ' checked' : ''}`}><label><input type="checkbox" checked={completedResearch.includes(step.id)} onChange={() => toggleResearch(step.id)}/><span><b>{step.title}</b><small>{step.tip}</small></span></label><button type="button" className="invest-lesson-link" onClick={() => onLearn(step.lessonId)} aria-label={`Read lesson for ${step.title}`}>Read lesson <ArrowRight size={14}/></button></div>)}</div>
            <p className="invest-research-foot">Your ticks are saved in this browser for this share. Paperlane does not verify the research.</p>
          </section>
        </> : <div className="invest-empty">No equity instrument is active. Add a share from the terminal to start exploring.</div>}
      </div>
    </div>

    <section className="invest-concentration invest-panel" aria-label="Paper share concentration">
      <div className="invest-concentration-head"><div><span className="invest-eyebrow"><ChartNoAxesCombined size={15}/> YOUR PAPER SHARE MIX</span><h3>Where is your share money placed?</h3><p>See how much of your long share holdings sits in each company.</p></div>{largestHolding&&<div className="invest-concentration-summary"><span>Largest holding <b>{largestHolding.allocation_pct.toFixed(1)}%</b></span><span>Top three <b>{topThreeAllocation.toFixed(1)}%</b></span></div>}</div>
      {!overview?<p className="invest-concentration-empty">Loading your paper share mix…</p>:holdings.length?<div className="invest-concentration-list">{holdings.map((holding,index)=><div className="invest-concentration-row" key={holding.symbol}><div><b>{equities.find(item=>item.symbol===holding.symbol)?.display_symbol||holding.symbol}</b><span>{money(holding.market_value)} · {holding.allocation_pct.toFixed(1)}%</span></div><div className="invest-concentration-track" role="img" aria-label={`${holding.name}: ${holding.allocation_pct.toFixed(1)} percent of long share holdings`}><i style={{width:`${Math.max(0,Math.min(100,holding.allocation_pct))}%`,backgroundColor:['#90e2b5','#87b9e6','#e9be84','#d0a8e7','#ed9c9d'][index%5]}}/></div></div>)}</div>:<p className="invest-concentration-empty">No long paper shares yet. When you buy a share in the simulator, its place in your share mix will appear here.</p>}
      <p className="invest-research-foot">Percentages use only long equity holdings. Cash, options and short positions are excluded. Companies can still move together, so this is a view of allocation, not a risk score.</p>
    </section>

    <section className="invest-research invest-panel"><div className="invest-research-head"><div><span className="invest-eyebrow"><CircleHelp size={15}/> A BETTER INVESTING QUESTION</span><h3>What would you check before buying a business?</h3></div><button type="button" onClick={() => onLearn()}>Study the basics <ArrowRight size={16}/></button></div><div className="invest-research-grid"><article><b>01 · Business</b><p>How does the company make money? What could weaken demand or its advantage?</p></article><article><b>02 · Financial health</b><p>Look for growth in sales and profit, cash flow, and debt over several years.</p></article><article><b>03 · Price and risk</b><p>Compare valuation with growth and peers. Decide how much of your portfolio one idea deserves.</p></article></div><p className="invest-research-foot">Paperlane does not yet ingest company filings or verified fundamentals. Check original exchange filings and annual reports before drawing real-world conclusions.</p></section>

    {holdings.length > 0 && <section className="invest-panel invest-holdings"><div className="invest-panel-title"><div><span>YOUR PAPER ACCOUNT</span><h3>Share holdings</h3></div></div><div className="invest-holdings-list">{holdings.map(position => <button type="button" key={position.symbol} onClick={() => showHoldingChart(position.symbol)} aria-label={`View chart for ${equities.find(item => item.symbol === position.symbol)?.display_symbol || position.symbol}`}><span><b>{equities.find(item => item.symbol === position.symbol)?.display_symbol || position.symbol}</b><small>{position.quantity.toLocaleString('en-IN')} shares · Average {money(position.average_price)} · {position.allocation_pct.toFixed(1)}% of share holdings</small></span><span><b>{money(position.market_value)}</b><small className={position.unrealized_pnl < 0 ? 'invest-loss' : 'invest-gain'}>{money(position.unrealized_pnl)} open</small></span></button>)}</div><p className="invest-research-foot">Select a holding to view its chart above. These holdings share your existing paper trading account and balance.</p></section>}
  </div>;
}
