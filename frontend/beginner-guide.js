/* Guided practice is a teaching layer. It never sends an order or changes account data. */
(() => {
  'use strict';
  const key='paperlane.beginner-guide.v1';
  const dialog=document.getElementById('beginner-guide');
  const content=document.getElementById('guide-content');
  const start=document.getElementById('guide-start');
  const resume=document.getElementById('guide-resume');
  const steps=[
    {title:'Choose a share',body:'A share is a small part of a company. Start with a share rather than an option while you learn the buttons. Watch the company name and exchange so you know which instrument is selected.',action:'Show me a share',target:'share'},
    {title:'Read the quote',body:'The bid is what a buyer offers. The ask is what a seller wants. An immediate paper buy uses the ask; an immediate paper sell uses the bid. The gap is the spread, a cost to notice even if the displayed price barely moves.',action:'Show the quote',target:'quote'},
    {title:'Prepare your order',body:'Before you submit, check the instrument, BUY or SELL, quantity, order type and estimated amount. Write down why you would enter and when you would leave. A market order aims to fill now; a limit order can wait or never fill. The app will not submit anything for you.',action:'Show the order ticket',target:'ticket'},
    {title:'Find your position',body:'After a paper order fills, Positions shows what you still hold and its changing open profit or loss. A pending order appears in Orders instead. A prepared exit only fills when you review and submit the opposite-side paper order yourself.',action:'Open positions',target:'positions'},
    {title:'Review the result',body:'Once a position is closed, Trade report shows the entry, exit, quantity, fees and final result. Ask whether you followed your plan. One profitable paper trade does not prove a strategy works.',action:'Open trade report',target:'report'}
  ];
  let step=-1;
  try{const saved=Number(localStorage.getItem(key));if(Number.isInteger(saved)&&saved>=0&&saved<steps.length)step=saved;}catch(error){}
  function persist(){try{if(step<0)localStorage.removeItem(key);else localStorage.setItem(key,String(step));}catch(error){}}
  function label(){start.textContent=step<0?'Start guided practice':'Continue guided practice';resume.hidden=step<0;}
  function render(){const item=steps[step];if(!item)return;const selectedShare=typeof orderInstrument==='function'?orderInstrument():null;const quote=selectedShare&&selectedShare.kind==='EQUITY'?`<p class="guide-quote">Current practice quote: bid <b>${money(selectedShare.bid)}</b> · ask <b>${money(selectedShare.ask)}</b>. Prices here are synthetic.</p>`:'';
    const positionCount=typeof state!=='undefined'&&state?state.positions.length:0;
    const positionNote=step===3?`<p class="guide-quote">${positionCount?`You have ${positionCount} open paper position${positionCount===1?'':'s'} to inspect.`:'You have no open paper position yet. You can still open the Positions view and return here later.'}</p>`:'';
    content.innerHTML=`<div class="guide-top"><span>GUIDED PRACTICE · ${step+1} OF ${steps.length}</span><button type="button" data-guide="close" aria-label="Close guide">Close ×</button></div><progress max="${steps.length}" value="${step+1}" aria-label="Guide progress"></progress><h2 id="guide-title">${item.title}</h2><p>${item.body}</p>${step===1?quote:''}${positionNote}<div class="guide-actions"><button type="button" data-guide="action" class="quiet">${item.action}</button><button type="button" data-guide="next" class="primary">${step===steps.length-1?'Finish guide':'Next step'}</button></div><p class="guide-foot">Move at your own pace. Next step records only your place in the guide; it does not place a trade.</p><button type="button" data-guide="restart" class="guide-restart">Start again</button>`;
  }
  function open(){if(step<0){step=0;persist();label();}render();if(!dialog.open)dialog.showModal();}
  function navigate(target){dialog.close();if(target==='share'){const share=state?.instruments.find(i=>i.kind==='EQUITY');if(share)select(share.symbol);document.getElementById('terminal').scrollIntoView({behavior:'smooth',block:'start'});}
    if(target==='quote')document.querySelector('.chart-panel').scrollIntoView({behavior:'smooth',block:'start'});
    if(target==='ticket')document.getElementById('order-ticket').scrollIntoView({behavior:'smooth',block:'start'});
    if(target==='positions'||target==='report'){document.querySelector(`[data-tab="${target}"]`).click();document.getElementById('activity').scrollIntoView({behavior:'smooth',block:'start'});}
  }
  start.addEventListener('click',open);resume.addEventListener('click',open);
  dialog.addEventListener('click',event=>{const button=event.target.closest('[data-guide]');if(!button)return;const kind=button.dataset.guide;if(kind==='close'){dialog.close();return;}if(kind==='action'){navigate(steps[step].target);return;}if(kind==='restart'){step=0;persist();render();return;}if(kind==='next'){if(step===steps.length-1){step=-1;persist();dialog.close();label();return;}step++;persist();render();}});
  label();
})();
