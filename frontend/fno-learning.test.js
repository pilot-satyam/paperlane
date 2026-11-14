const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/learning.js','utf8');
const start=source.indexOf('function expiryPayoff(');
const end=source.indexOf('function paintFnoPayoff()',start);
assert.ok(start>=0&&end>start);
const payoff=vm.runInNewContext(source.slice(start,end)+'\nexpiryPayoff');
test('bought call can be in the money and still lose after premium',()=>{
 const x=payoff('call','buy',100,8,50,1,105);
 assert.equal(x.intrinsic,5);assert.equal(x.unit,-3);assert.equal(x.total,-150);assert.equal(x.breakeven,108);assert.equal(x.premiumAmount,400);
});
test('bought put and written call have opposite payoff directions',()=>{
 assert.equal(payoff('put','buy',100,5,50,2,90).total,500);
 assert.equal(payoff('call','sell',100,8,50,1,150).total,-2100);
});
test('reject missing or invalid contract inputs',()=>{
 for(const args of [['call','buy',100,8,0,1,105],['call','buy',100,8,1.5,1,105],['call','buy',100,8,50,1,-1],['future','buy',100,8,50,1,105]])assert.equal(payoff(...args),null);
});
test('put premium above strike has no nonnegative expiry break-even',()=>{
 assert.equal(payoff('put','buy',100,120,50,1,0).breakeven,null);
 assert.equal(payoff('put','buy',100,100,50,1,0).breakeven,0);
});
