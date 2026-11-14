import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowUpRight, Plus, Search, X } from 'lucide-react';
import { api, money } from '../api';
import type { Instrument } from '../types';
import './HeaderStockSearch.css';

type Listing = { id:string; trading_symbol:string; name:string; exchange:'NSE'|'BSE'; series?:string; can_simulate:boolean; restriction?:string };
type Catalogue = { items:Listing[]; total:number };

const score = (symbol:string, name:string, query:string) => {
  const code=symbol.toLowerCase(), title=name.toLowerCase();
  return code===query?0:code.startsWith(query)?1:title.startsWith(query)?2:code.includes(query)?3:4;
};

export default function HeaderStockSearch({instruments,onOpenChart,onRefresh}:{instruments:Instrument[];onOpenChart:(symbol:string)=>void;onRefresh:()=>Promise<void>}){
  const [query,setQuery]=useState('');
  const [open,setOpen]=useState(false);
  const [catalogue,setCatalogue]=useState<Catalogue|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [working,setWorking]=useState('');
  const root=useRef<HTMLDivElement>(null);
  const input=useRef<HTMLInputElement>(null);
  const term=query.trim().toLowerCase();

  useEffect(()=>{
    if(!open||term.length<2){setCatalogue(null);setLoading(false);setError('');return;}
    let active=true;
    setLoading(true);
    setCatalogue(null);
    const timer=window.setTimeout(()=>{
      const params=new URLSearchParams({q:term,exchange:'ALL',offset:'0',limit:'40'});
      api<Catalogue>('/api/catalogue?'+params).then(result=>{if(active){setCatalogue(result);setError('');}})
        .catch(e=>{if(active){setError(e instanceof Error?e.message:'Search is unavailable.');setCatalogue(null);}})
        .finally(()=>{if(active)setLoading(false);});
    },240);
    return()=>{active=false;window.clearTimeout(timer);};
  },[open,term]);

  useEffect(()=>{
    const outside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};
    document.addEventListener('pointerdown',outside);
    return()=>document.removeEventListener('pointerdown',outside);
  },[]);

  const active=instruments.filter(item=>item.kind!=='OPTION'&&(!term||`${item.symbol} ${item.display_symbol||''} ${item.name}`.toLowerCase().includes(term)))
    .sort((a,b)=>score(a.trading_symbol||a.symbol,a.name,term)-score(b.trading_symbol||b.symbol,b.name,term))
    .slice(0,5);
  const activeIds=new Set(instruments.map(item=>item.catalogue_id).filter(Boolean));
  const activeCodes=new Set(instruments.filter(item=>item.kind==='EQUITY').map(item=>`${(item.trading_symbol||item.symbol).toLowerCase()}:${item.exchange||'NSE'}`));
  const listings=(catalogue?.items||[]).filter(item=>!activeIds.has(item.id)&&!activeCodes.has(`${item.trading_symbol.toLowerCase()}:${item.exchange}`))
    .sort((a,b)=>score(a.trading_symbol,a.name,term)-score(b.trading_symbol,b.name,term)||Number(b.can_simulate)-Number(a.can_simulate))
    .slice(0,6);

  const close=()=>{setOpen(false);setQuery('');input.current?.blur();};
  const select=(symbol:string)=>{close();onOpenChart(symbol);};
  const activate=async(item:Listing)=>{
    if(!item.can_simulate||working)return;
    setWorking(item.id);
    try{
      const result=await api<{symbol:string}>('/api/catalogue/activate',{id:item.id});
      await onRefresh();
      select(result.symbol);
    }catch(e){setError(e instanceof Error?e.message:'Could not add this listing.');}
    finally{setWorking('');}
  };
  const onInputKeyDown=(event:KeyboardEvent<HTMLInputElement>)=>{
    if(event.key==='Escape'){close();return;}
    if(event.key==='ArrowDown'){
      event.preventDefault();
      root.current?.querySelector<HTMLButtonElement>('.header-search-result:not(:disabled)')?.focus();
    }
    if(event.key==='Enter'){
      if(active.length){event.preventDefault();select(active[0].symbol);}
      else if(listings.some(item=>item.can_simulate)){
        event.preventDefault();
        void activate(listings.find(item=>item.can_simulate)!);
      }
    }
  };

  return <div className={`header-search${open?' open':''}`} ref={root} onBlur={event=>{if(!root.current?.contains(event.relatedTarget as Node))setOpen(false);}} onKeyDown={event=>{if(event.key==='Escape')close();}}>
    <button type="button" className="header-search-toggle" aria-label="Search stocks" aria-expanded={open} onClick={()=>{setOpen(true);window.setTimeout(()=>input.current?.focus(),0);}}><Search size={18}/></button>
    <div className="header-search-field"><Search size={17} aria-hidden="true"/><input ref={input} type="search" value={query} maxLength={200} placeholder="Search stocks or companies" aria-label="Search stocks or companies" aria-expanded={open} aria-controls="header-stock-results" onFocus={()=>setOpen(true)} onChange={event=>setQuery(event.target.value)} onKeyDown={onInputKeyDown}/>{query&&<button type="button" aria-label="Clear stock search" onClick={()=>{setQuery('');input.current?.focus();}}><X size={15}/></button>}</div>
    {open&&<div className="header-search-popover" id="header-stock-results" role="region" aria-label="Stock search results">
      <div className="header-search-title">YOUR PRACTICE DESK <span>{term?'Matching instruments':'Quick access'}</span></div>
      {active.length?<div className="header-search-list">{active.map(item=><button className="header-search-result" type="button" key={item.symbol} onClick={()=>select(item.symbol)}><span className="header-search-symbol">{(item.trading_symbol||item.symbol).slice(0,2)}</span><span className="header-search-name"><b>{item.display_symbol||item.trading_symbol||item.symbol}</b><small>{item.name} · {item.kind==='INDEX'?'Index':item.exchange||'NSE'}</small></span><span className="header-search-price">{money(item.ltp)}<ArrowUpRight size={14}/></span></button>)}</div>:<p className="header-search-empty">No matching instrument on your desk.</p>}
      {term.length>=2&&<><div className="header-search-title">NSE & BSE CATALOGUE <span>Dated snapshot</span></div>{loading?<p className="header-search-empty">Searching listings…</p>:error?<p className="header-search-error" role="status">{error}</p>:listings.length?<div className="header-search-list">{listings.map(item=><button className="header-search-result" type="button" key={item.id} disabled={!item.can_simulate||!!working} title={item.restriction||undefined} onClick={()=>void activate(item)}><span className="header-search-symbol">{item.exchange==='NSE'?'NS':'BS'}</span><span className="header-search-name"><b>{item.trading_symbol||item.name}</b><small>{item.name} · {item.exchange}</small></span><span className="header-search-action">{working===item.id?'Adding…':item.can_simulate?'Add & open':'View only'}{item.can_simulate&&<Plus size={13}/>}</span></button>)}</div>:<p className="header-search-empty">No other listings found. Try a company name or symbol.</p>}</>}
      <p className="header-search-foot">Prices are synthetic. Catalogue listings are a dated snapshot, not live market data.</p>
    </div>}
  </div>;
}
