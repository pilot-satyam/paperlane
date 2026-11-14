/* Explain ledger arithmetic. These rules do not infer market causation or intent. */
(function(root){
'use strict';
function describe(t){
  const move=Number(t.exit_price)-Number(t.entry_price),direction=t.direction==='SHORT'?-1:1;
  const perUnit=move*direction, fees=Number(t.fees),net=Number(t.net_pnl),quantity=Number(t.quantity);
  let reason;
  if(perUnit>0)reason=t.direction==='SHORT'?'You bought back lower than you sold. That price move helped your short position.':'You sold higher than you bought. That price move helped your long position.';
  else if(perUnit<0)reason=t.direction==='SHORT'?'You bought back higher than you sold. That price move went against your short position.':'You sold lower than you bought. That price move went against your long position.';
  else reason='Your entry and exit prices were equal. There was no gross gain from the price move.';
  if(perUnit>=0&&net<0)reason+=' Charges were enough to turn the result into a net loss.';
  const improvements=[];
  if(perUnit>=0&&net<0)improvements.push('Before the next practice trade, estimate round-trip costs and compare them with your planned target. A small favourable move can still lose after costs.');
  else if(perUnit<0)improvements.push('Compare the actual exit with your planned invalidation level. If no level was recorded, write one before the next practice trade; a stop can still slip or fail to fill.');
  else improvements.push('Check whether this exit followed a plan recorded before entry. Keep the same review process for losing trades; one profitable result is not evidence of an edge.');
  improvements.push('Check size in units, not just lots. Each ₹1 move changes this position’s gross value by ₹'+quantity.toLocaleString('en-IN')+'. Choose practice size deliberately.');
  improvements.push('Use indicators as context, not a verdict. Record your timeframe and signal before entering, then compare them with the saved entry snapshot.');
  return {reason,perUnit,quantity,fees,net,improvements};
}
if(typeof module!=='undefined'&&module.exports)module.exports={describe};else root.PaperlaneReview={describe};
})(typeof window!=='undefined'?window:globalThis);
