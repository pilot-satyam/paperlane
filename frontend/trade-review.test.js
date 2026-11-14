const test=require('node:test'),assert=require('node:assert/strict');
const {describe}=require('./trade-review.js');
test('long profit explains favourable price movement and units',()=>{const r=describe({direction:'LONG',entry_price:349.7,exit_price:368.75,quantity:125,fees:44.91,net_pnl:2336.34});assert.match(r.reason,/sold higher/);assert.ok(Math.abs(r.perUnit-19.05)<1e-8);assert.equal(r.quantity,125);});
test('short loss explains buyback in correct direction',()=>{const r=describe({direction:'SHORT',entry_price:100,exit_price:105,quantity:10,fees:1,net_pnl:-51});assert.equal(r.perUnit,-5);assert.match(r.reason,/bought back higher/);});
test('small favourable move can lose to fees',()=>{const r=describe({direction:'LONG',entry_price:100,exit_price:101,quantity:1,fees:2,net_pnl:-1});assert.match(r.reason,/Charges/);assert.match(r.improvements[0],/round-trip costs/);});
test('flat price identifies costs without inventing an adverse signal',()=>{const r=describe({direction:'LONG',entry_price:100,exit_price:100,quantity:1,fees:2,net_pnl:-2});assert.equal(r.perUnit,0);assert.match(r.reason,/equal/);});
