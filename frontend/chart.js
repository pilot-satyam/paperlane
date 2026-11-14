/* Paperlane chart adapter. TradingView Lightweight Charts is vendored under Apache-2.0. */
(function(root){
'use strict';
function aggregateTicks(history,intervalSeconds){
  if(!Number.isFinite(intervalSeconds)||intervalSeconds<=0)throw new Error('Interval must be positive');
  const ticks=(Array.isArray(history)?history:[]).map((p,index)=>({time:typeof p.time==='number'?p.time:Date.parse(p.time)/1000,value:typeof p.value==='number'?p.value:Number(p.value),index,valid:p.value!==null&&p.value!==''&&p.value!==undefined})).filter(p=>p.valid&&Number.isFinite(p.time)&&Number.isFinite(p.value)&&p.value>0).sort((a,b)=>a.time-b.time||a.index-b.index);
  const bars=[];for(const tick of ticks){const time=Math.floor(tick.time/intervalSeconds)*intervalSeconds;let bar=bars[bars.length-1];if(!bar||bar.time!==time){bar={time,open:tick.value,high:tick.value,low:tick.value,close:tick.value};bars.push(bar);}else{bar.high=Math.max(bar.high,tick.value);bar.low=Math.min(bar.low,tick.value);bar.close=tick.value;}}
  return bars;
}
function movingAverage(bars,period){if(!Number.isInteger(period)||period<1)throw new Error('Period must be a positive integer');let sum=0;const values=[];bars.forEach((bar,index)=>{sum+=bar.close;if(index>=period)sum-=bars[index-period].close;if(index>=period-1)values.push({time:bar.time,value:sum/period});});return values;}
// Indicators consume observed closes in chronological order; missing intervals are not invented.
function exponentialMovingAverage(bars,period=20){
 if(!Number.isInteger(period)||period<1)throw new Error('Period must be a positive integer');
 if(bars.length<period)return [];let value=bars.slice(0,period).reduce((sum,b)=>sum+b.close,0)/period;
 const output=[{time:bars[period-1].time,value}],alpha=2/(period+1);
 for(let i=period;i<bars.length;i++){value=alpha*bars[i].close+(1-alpha)*value;output.push({time:bars[i].time,value});}return output;
}
function relativeStrengthIndex(bars,period=14){
 if(!Number.isInteger(period)||period<1)throw new Error('Period must be a positive integer');
 if(bars.length<=period)return [];let gain=0,loss=0;const output=[];
 const value=()=>gain===0&&loss===0?50:loss===0?100:100-100/(1+gain/loss);
 for(let i=1;i<=period;i++){const delta=bars[i].close-bars[i-1].close;gain+=Math.max(0,delta)/period;loss+=Math.max(0,-delta)/period;}
 output.push({time:bars[period].time,value:value()});
 for(let i=period+1;i<bars.length;i++){const delta=bars[i].close-bars[i-1].close;gain=(gain*(period-1)+Math.max(0,delta))/period;loss=(loss*(period-1)+Math.max(0,-delta))/period;output.push({time:bars[i].time,value:value()});}return output;
}
function validateRsiSettings(settings){
  return !!settings&&Number.isInteger(settings.period)&&settings.period>=2&&settings.period<=200&&Number.isFinite(settings.lower)&&Number.isFinite(settings.upper)&&settings.lower>=0&&settings.upper<=100&&settings.lower<settings.upper;
}
function validateIndicatorSettings(type,s){return ['sma','ema','rsi'].includes(type)&&!!s&&Number.isInteger(s.period)&&s.period>=2&&s.period<=200&&/^#[0-9a-f]{6}$/i.test(s.color)&&Number.isInteger(s.width)&&s.width>=1&&s.width<=4&&(type!=='rsi'||validateRsiSettings(s));}
function validateDrawings(value){return Array.isArray(value)?value.slice(-50).filter(d=>d&&['horizontal','trend'].includes(d.type)&&Array.isArray(d.points)&&d.points.length===(d.type==='horizontal'?1:2)&&d.points.every(p=>Number.isFinite(p.time)&&p.time>0&&Number.isFinite(p.price)&&p.price>0)&& (d.type!=='trend'||d.points[0].time!==d.points[1].time)).map(d=>({type:d.type,points:d.points.map(p=>({time:p.time,price:p.price}))})):[];}
// Reserve empty time slots for short histories instead of stretching a few candles.
function fittedRange(count,width){
  const slots=Math.max(40,Math.ceil(Math.max(0,width)/10),count+4);
  const to=Math.max(0,count-1)+4;
  return {from:to-slots,to};
}
if(typeof module!=='undefined'&&module.exports){module.exports={aggregateTicks,movingAverage,fittedRange,exponentialMovingAverage,relativeStrengthIndex,validateDrawings,validateRsiSettings,validateIndicatorSettings};return;}
const byId=id=>document.getElementById(id);let chart,candles,line,sma,ema,rsi,host,seriesData=[],currentInstrument,currentHistory=[],interval=10,kind='candles',smaEnabled=false,lastSymbol,hoverTime=null,emaEnabled=false,rsiEnabled=false,drawings=[],drawMode='',firstAnchor=null,drawingSvg,lastOverlay='',replayTrade=null,rsiSettings={period:14,lower:30,upper:70},rsiLevels=[];
try{const saved=JSON.parse(localStorage.getItem('paperlane.rsi.v1'));if(validateRsiSettings(saved))rsiSettings={period:saved.period,lower:saved.lower,upper:saved.upper};}catch(error){}
const indicators={sma:{period:10,color:'#e3ba7c',width:1,enabled:false},ema:{period:20,color:'#81bde3',width:2,enabled:false},rsi:{...rsiSettings,color:'#d5a5ed',width:2,enabled:false}};
try{const saved=JSON.parse(localStorage.getItem('paperlane.indicators.v1'));for(const type of Object.keys(indicators)){if(validateIndicatorSettings(type,saved?.[type]))indicators[type]={...saved[type],enabled:saved[type].enabled===true};}}catch(error){}
const price=v=>Number(v).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:4});
const clock=t=>new Date(Number(t)*1000).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
function legend(time){const bar=time?seriesData.find(b=>b.time===time):seriesData.at(-1);const element=byId('chart-ohlc');if(!element)return;element.textContent=bar?`${clock(bar.time)} IST  O ${price(bar.open)}  H ${price(bar.high)}  L ${price(bar.low)}  C ${price(bar.close)}`:'Waiting for observed synthetic ticks…';}
function initialize(){
  if(chart)return true;host=byId('chart');if(!host)return false;
  if(!root.LightweightCharts){host.textContent='Chart library unavailable. Reload to retry; quotes and orders remain separate.';return false;}
  host.innerHTML='<div id="chart-canvas" tabindex="0" aria-label="Synthetic price chart. Drag to pan, scroll or pinch to zoom. Use Fit and Latest buttons to navigate."></div><p id="chart-history-note" class="chart-history-note"></p><div class="chart-attribution">TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc. <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView</a></div>';
  const L=root.LightweightCharts;
  chart=L.createChart(byId('chart-canvas'),{autoSize:true,layout:{background:{type:'solid',color:'#131820'},textColor:'#99a5b7',fontSize:10,attributionLogo:true},grid:{vertLines:{color:'#1e2a32'},horzLines:{color:'#233039'}},rightPriceScale:{borderColor:'#30404a',scaleMargins:{top:0.12,bottom:0.12}},timeScale:{borderColor:'#30404a',timeVisible:true,secondsVisible:true,rightOffset:4,barSpacing:9,minBarSpacing:2,tickMarkFormatter:clock},localization:{locale:'en-IN',timeFormatter:t=>clock(t)+' IST'},crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#829c8c',labelBackgroundColor:'#344e40'},horzLine:{color:'#829c8c',labelBackgroundColor:'#344e40'}},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
  candles=chart.addSeries(L.CandlestickSeries,{upColor:'#81dfb6',downColor:'#f08d91',borderVisible:false,wickUpColor:'#81dfb6',wickDownColor:'#f08d91'});
  line=chart.addSeries(L.LineSeries,{color:'#81dfb6',lineWidth:2,visible:false,lastValueVisible:false,priceLineVisible:false});
  sma=chart.addSeries(L.LineSeries,{color:'#e3ba7c',lineWidth:1,visible:false,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  ema=chart.addSeries(L.LineSeries,{color:'#a6a0ff',lineWidth:2,visible:false,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  chart.subscribeClick(handleDrawingClick);
  drawingSvg=document.createElementNS('http://www.w3.org/2000/svg','svg');drawingSvg.classList.add('chart-drawing-overlay');drawingSvg.setAttribute('aria-hidden','true');byId('chart-canvas').appendChild(drawingSvg);
  function overlayFrame(){renderDrawingOverlay();root.requestAnimationFrame(overlayFrame);}root.requestAnimationFrame(overlayFrame);
  chart.subscribeCrosshairMove(param=>{hoverTime=typeof param.time==='number'?param.time:null;legend(hoverTime);});
  byId('chart-interval').addEventListener('change',event=>{interval=Number(event.target.value);seriesData=[];draw(true);});
  byId('chart-style').addEventListener('change',event=>{kind=event.target.value;candles.applyOptions({visible:kind==='candles'});line.applyOptions({visible:kind==='line',lastValueVisible:kind==='line',priceLineVisible:kind==='line'});});
  byId('chart-indicators').onclick=()=>openIndicator('sma');
  byId('indicator-close').onclick=()=>byId('indicator-dialog').close();
  byId('indicator-type').onchange=()=>fillIndicatorForm();
  byId('indicator-form').onsubmit=event=>{event.preventDefault();const type=byId('indicator-type').value;const config={period:Number(byId('indicator-period').value),color:byId('indicator-color').value,width:Number(byId('indicator-width').value),enabled:true};if(type==='rsi'){config.lower=Number(byId('indicator-lower').value);config.upper=Number(byId('indicator-upper').value);}if(!validateIndicatorSettings(type,config)){byId('indicator-status').textContent='Use a period from 2 to 200 and keep the lower RSI level below the upper level.';return;}indicators[type]=config;syncIndicators();saveIndicators();byId('indicator-dialog').close();};
  byId('indicator-remove').onclick=()=>{indicators[byId('indicator-type').value].enabled=false;syncIndicators();saveIndicators();byId('indicator-dialog').close();};
  syncIndicators();
  byId('chart-level').onclick=()=>setDrawMode('horizontal');byId('chart-trend').onclick=()=>setDrawMode('trend');byId('chart-cancel-draw').onclick=()=>setDrawMode('');
  byId('chart-undo').onclick=()=>{drawings.pop();setDrawMode('');saveDrawings();};byId('chart-clear').onclick=()=>{if(drawings.length&&!root.confirm('Clear the saved drawing annotations for this instrument?'))return;drawings=[];setDrawMode('');saveDrawings();};
  byId('chart-fit').onclick=()=>{fitObservedHistory();};
  byId('chart-latest').onclick=()=>chart.timeScale().scrollToRealTime();
  byId('chart-canvas').addEventListener('keydown',event=>{if(event.key==='Escape'){setDrawMode('');return;}const range=chart.timeScale().getVisibleLogicalRange();if(!range)return;let next;if(event.key==='ArrowLeft'||event.key==='ArrowRight'){const delta=(range.to-range.from)*.15*(event.key==='ArrowLeft'?-1:1);next={from:range.from+delta,to:range.to+delta};}else if(event.key==='+'||event.key==='='||event.key==='-'){const middle=(range.to+range.from)/2,half=(range.to-range.from)/2*(event.key==='-'?1.2:.8);next={from:middle-half,to:middle+half};}if(next){event.preventDefault();chart.timeScale().setVisibleLogicalRange(next);}});
  return true;
}
function openIndicator(type){byId('indicator-type').value=type;fillIndicatorForm();byId('indicator-dialog').showModal();}
function fillIndicatorForm(){const type=byId('indicator-type').value,config=indicators[type];byId('indicator-period').value=config.period;byId('indicator-color').value=config.color;byId('indicator-width').value=config.width;byId('indicator-levels').hidden=type!=='rsi';byId('indicator-lower').disabled=type!=='rsi';byId('indicator-upper').disabled=type!=='rsi';byId('indicator-lower').value=indicators.rsi.lower;byId('indicator-upper').value=indicators.rsi.upper;byId('indicator-apply').textContent=config.enabled?'Apply changes':'Add to chart';byId('indicator-remove').hidden=!config.enabled;byId('indicator-status').textContent='';byId('indicator-description').textContent={sma:'Average closing price over your chosen number of observed bars.',ema:'A moving average that gives more weight to recent closing prices.',rsi:'Momentum on a 0–100 scale, with custom reference levels.'}[type];}
function saveIndicators(){try{localStorage.setItem('paperlane.indicators.v1',JSON.stringify(indicators));}catch(error){byId('chart-draw-help').textContent='Indicator settings apply for this session only; browser storage is unavailable.';}}
function syncIndicators(){
 const range=chart.timeScale().getVisibleLogicalRange();smaEnabled=indicators.sma.enabled;emaEnabled=indicators.ema.enabled;rsiEnabled=indicators.rsi.enabled;rsiSettings=indicators.rsi;
 for(const [type,series] of [['sma',sma],['ema',ema]]){const c=indicators[type];series.applyOptions({visible:c.enabled,color:c.color,lineWidth:c.width});}
 if(rsiEnabled&&!rsi){rsi=chart.addSeries(root.LightweightCharts.LineSeries,{priceLineVisible:false,lastValueVisible:true,priceFormat:{type:'price',precision:1,minMove:.1},autoscaleInfoProvider:()=>({priceRange:{minValue:0,maxValue:100}})},1);chart.panes()[1].setHeight(180);}
 if(rsiEnabled){rsi.applyOptions({color:rsiSettings.color,lineWidth:rsiSettings.width,crosshairMarkerRadius:5});rsi.priceScale().applyOptions({scaleMargins:{top:.08,bottom:.08}});updateRsiLevels();}else if(rsi){chart.removeSeries(rsi);rsi=null;rsiLevels=[];}
 host.classList.toggle('with-rsi',rsiEnabled);
 const chips=byId('active-indicators');chips.replaceChildren();for(const [type,c] of Object.entries(indicators)){if(!c.enabled)continue;const button=document.createElement('button');button.type='button';button.textContent=type.toUpperCase()+' '+c.period+' · Edit';button.setAttribute('aria-label','Edit '+type.toUpperCase()+' indicator');button.style.borderColor=c.color;button.onclick=()=>openIndicator(type);chips.appendChild(button);}
 draw(false);if(range)chart.timeScale().setVisibleLogicalRange(range);
}
function updateRsiLevels(){if(!rsi)return;rsiLevels.forEach(level=>rsi.removePriceLine(level));rsiLevels=[rsi.createPriceLine({price:rsiSettings.upper,color:'#edb56a',lineWidth:2,lineStyle:0,axisLabelVisible:true,axisLabelColor:'#edb56a',axisLabelTextColor:'#111820',title:''}),rsi.createPriceLine({price:rsiSettings.lower,color:'#72d8b0',lineWidth:2,lineStyle:0,axisLabelVisible:true,axisLabelColor:'#72d8b0',axisLabelTextColor:'#111820',title:''})];}
function fitObservedHistory(){
  chart.timeScale().setVisibleLogicalRange(fittedRange(seriesData.length,byId('chart-canvas').clientWidth));
  chart.priceScale('right').applyOptions({autoScale:true});
}
function draw(fit){
  if(!chart)return;const previous=seriesData,range=chart.timeScale().getVisibleLogicalRange();const bars=aggregateTicks(currentHistory,interval);seriesData=bars;
  const tick=Number(currentInstrument?.tick_size)||.01,precision=Math.min(8,Math.max(2,(String(tick).split('.')[1]||'').length));candles.applyOptions({priceFormat:{type:'price',precision,minMove:tick}});line.applyOptions({priceFormat:{type:'price',precision,minMove:tick}});
  candles.setData(bars);line.setData(bars.map(b=>({time:b.time,value:b.close})));sma.setData(movingAverage(bars,indicators.sma.period));ema.setData(exponentialMovingAverage(bars,indicators.ema.period));if(rsi)rsi.setData(relativeStrengthIndex(bars,rsiSettings.period));
  if(fit||!previous.length){fitObservedHistory();}
  else if(range&&bars.length){const following=range.to>=previous.length-1;let shift=0;if(following){shift=bars.length-previous.length;}else{const dropped=previous.findIndex(b=>b.time>=bars[0].time);shift=dropped<0?0:-dropped;}chart.timeScale().setVisibleLogicalRange({from:range.from+shift,to:range.to+shift});}
  const count=bars.length;byId('chart-history-note').textContent=`${count} observed ${interval===10?'10-second':interval===60?'1-minute':'5-minute'} bar${count===1?'':'s'} · Synthetic ticks only · Latest bar may be forming · No volume feed${smaEnabled&&count<indicators.sma.period?' · SMA '+indicators.sma.period+' needs '+indicators.sma.period+' observed bars':''}${emaEnabled&&count<indicators.ema.period?' · EMA '+indicators.ema.period+' needs '+indicators.ema.period+' observed bars':''}${rsiEnabled&&count<rsiSettings.period+1?' · RSI '+rsiSettings.period+' needs '+(rsiSettings.period+1)+' observed bars':''} · Indicators count observed bars; gaps are not filled`;legend(hoverTime);
}
function drawingKey(){return 'paperlane.drawings.v1.'+encodeURIComponent(currentInstrument.symbol);}
function loadDrawings(){try{const raw=localStorage.getItem(drawingKey());drawings=raw&&raw.length<100000?validateDrawings(JSON.parse(raw)):[];}catch(error){drawings=[];}lastOverlay='';}
function saveDrawings(){try{localStorage.setItem(drawingKey(),JSON.stringify(drawings));}catch(error){byId('chart-draw-help').textContent='Drawing saved for this session only; browser storage is unavailable.';}lastOverlay='';}
function setDrawMode(mode){drawMode=mode;firstAnchor=null;byId('chart-level').setAttribute('aria-pressed',mode==='horizontal');byId('chart-trend').setAttribute('aria-pressed',mode==='trend');byId('chart-cancel-draw').hidden=!mode;byId('chart-draw-help').textContent=mode==='horizontal'?'Click the price pane to place a horizontal level. Esc cancels.':mode==='trend'?'Click two different observed bars in the price pane to draw a trend line. Esc cancels.':'Drawings are personal annotations, saved in this browser per instrument. RSI uses its own 0–100 pane.';}
function handleDrawingClick(param){if(!drawMode||!param.point||typeof param.time!=='number'||(param.paneIndex!==undefined&&param.paneIndex!==0))return;if(!seriesData.some(b=>b.time===param.time))return;const value=(kind==='line'?line:candles).coordinateToPrice(param.point.y);if(!Number.isFinite(value)||value<=0)return;const anchor={time:param.time,price:value};if(drawMode==='trend'&&!firstAnchor){firstAnchor=anchor;byId('chart-draw-help').textContent='First anchor placed. Click a different observed bar for the second anchor.';return;}if(drawMode==='trend'&&anchor.time===firstAnchor.time){byId('chart-draw-help').textContent='Choose a different bar for the second trend-line anchor.';return;}if(drawings.length>=50){byId('chart-draw-help').textContent='Maximum 50 drawings per instrument. Undo or clear some first.';return;}drawings.push({type:drawMode,points:drawMode==='horizontal'?[anchor]:[firstAnchor,anchor]});saveDrawings();setDrawMode('');}
function renderDrawingOverlay(){if(!chart||!drawingSvg)return;const width=chart.timeScale().width(),height=chart.panes()[0].getHeight();drawingSvg.setAttribute('width',width);drawingSvg.setAttribute('height',height);const selectedSeries=kind==='line'?line:candles;const project=p=>{const time=Math.floor(p.time/interval)*interval,index=seriesData.findIndex(b=>b.time===time);if(index<0)return null;const x=chart.timeScale().logicalToCoordinate(index+(p.time-time)/interval),y=selectedSeries.priceToCoordinate(p.price);return x===null||y===null?null:{x,y};};let markup='';for(const d of drawings){if(d.type==='horizontal'){const y=selectedSeries.priceToCoordinate(d.points[0].price);if(y!==null)markup+=`<line x1="0" y1="${y}" x2="${width}" y2="${y}" stroke="#f0bf72" stroke-width="1.5" stroke-dasharray="6 4"/><text x="8" y="${y-5}" fill="#f0bf72" font-size="10">Level ${price(d.points[0].price)}</text>`;}else{const a=project(d.points[0]),b=project(d.points[1]);if(a&&b)markup+=`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#b3a7ff" stroke-width="2"/><circle cx="${a.x}" cy="${a.y}" r="3" fill="#b3a7ff"/><circle cx="${b.x}" cy="${b.y}" r="3" fill="#b3a7ff"/>`;}}
if(replayTrade){for(const [label,point,tone] of [['AVG ENTRY',replayTrade.entry,'#7ce0bb'],['EXIT',replayTrade.exit,'#f6bb77']]){if(!point)continue;const p=project(point);if(!p)continue;const labelX=Math.max(0,Math.min(width-104,p.x+6)),labelY=Math.max(16,Math.min(height-3,p.y-10));markup+=`<line x1="${p.x}" y1="0" x2="${p.x}" y2="${height}" stroke="${tone}" stroke-width="1" stroke-dasharray="4 4" opacity=".65"/><circle cx="${p.x}" cy="${p.y}" r="6" fill="${tone}" stroke="#111820" stroke-width="2"/><rect x="${labelX}" y="${labelY-13}" width="102" height="18" rx="4" fill="#111820" stroke="${tone}"/><text x="${labelX+5}" y="${labelY}" fill="${tone}" font-size="10" font-weight="700">${label} ${price(point.price)}</text>`;}}
if(firstAnchor){const a=project(firstAnchor);if(a)markup+=`<circle cx="${a.x}" cy="${a.y}" r="4" fill="#f0bf72"/>`;}if(markup!==lastOverlay){drawingSvg.innerHTML=markup;lastOverlay=markup;}}
root.renderTradingChart=function(instrument,history){currentInstrument=instrument;currentHistory=history||[];if(!initialize())return;const changed=lastSymbol!==instrument.symbol;if(changed){hoverTime=null;lastSymbol=instrument.symbol;replayTrade=null;setDrawMode('');loadDrawings();}draw(changed);};
root.showTradeOnChart=function(trade){
  if(!trade||!trade.symbol||typeof root.select!=='function')return false;
  root.select(trade.symbol);
  const locate=(at,value)=>{const seconds=Date.parse(at)/1000;const amount=Number(value);if(!Number.isFinite(seconds)||!Number.isFinite(amount)||amount<=0)return null;const bucket=Math.floor(seconds/interval)*interval;return seriesData.some(bar=>bar.time===bucket)?{time:seconds,price:amount}:null;};
  const entry=locate(trade.entry_at,trade.entry_price),exit=locate(trade.exit_at,trade.exit_price);
  replayTrade={entry,exit};lastOverlay='';
  const visible=[entry,exit].filter(Boolean).map(point=>seriesData.findIndex(bar=>bar.time===Math.floor(point.time/interval)*interval));
  if(visible.length){const from=Math.min(...visible),to=Math.max(...visible);chart.timeScale().setVisibleLogicalRange({from:Math.max(-5,from-8),to:Math.min(seriesData.length+4,Math.max(to+8,from+32))});}
  byId('chart-draw-help').textContent=visible.length===2?'Trade markers: green shows the weighted average entry price at the position start; amber shows the exit fill. Only saved synthetic chart history is shown.':visible.length===1?'Trade replay: one fill marker is visible. The other price bar is no longer in saved chart history.':'Trade replay unavailable: entry and exit bars are no longer in saved chart history. Trade prices remain in the report.';
  byId('chart').scrollIntoView({behavior:'smooth',block:'center'});
  return visible.length>0;
};
root.PaperlaneChartMath={aggregateTicks,movingAverage,exponentialMovingAverage,relativeStrengthIndex};
})(typeof window!=='undefined'?window:globalThis);
