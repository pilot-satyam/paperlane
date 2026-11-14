'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {aggregateTicks,movingAverage,fittedRange}=require('./chart.js');
const tick=(second,value)=>({time:new Date(second*1000).toISOString(),value});
test('OHLC follows tick timestamps rather than arrival order',()=>{
 assert.deepEqual(aggregateTicks([tick(19,103),tick(11,100),tick(12,105),tick(18,98),tick(21,102)],10),[
 {time:10,open:100,high:105,low:98,close:103},{time:20,open:102,high:102,low:102,close:102}]);
});
test('interval boundaries are exclusive and gaps are not fabricated',()=>{
 assert.deepEqual(aggregateTicks([tick(59,1),tick(60,2),tick(241,3)],60).map(b=>b.time),[0,60,240]);
 assert.deepEqual(aggregateTicks([tick(299,1),tick(300,2),tick(901,3)],300).map(b=>b.time),[0,300,900]);
});
test('one tick creates exactly one flat observed candle; empty history stays empty',()=>{
 assert.deepEqual(aggregateTicks([],10),[]);
 assert.deepEqual(aggregateTicks([tick(25,8)],10),[{time:20,open:8,high:8,low:8,close:8}]);
});
test('invalid dates and prices do not create prices or candles',()=>{
 assert.deepEqual(aggregateTicks([{time:'bad',value:2},tick(2,NaN),tick(3,null),tick(4,''),tick(5,-1),tick(6,0),tick(7,12)],10),[{time:0,open:12,high:12,low:12,close:12}]);
});
test('duplicate tick timestamps keep observed order and do not duplicate bars',()=>{
 assert.deepEqual(aggregateTicks([tick(1,10),tick(1,12),tick(1,11)],10),[{time:0,open:10,high:12,low:10,close:11}]);
});
test('SMA uses complete windows only and does not fabricate warmup values',()=>{
 const bars=aggregateTicks([tick(1,10),tick(11,20),tick(21,30),tick(31,40)],10);
 assert.deepEqual(movingAverage(bars,3),[{time:20,value:20},{time:30,value:30}]);
 assert.deepEqual(movingAverage(bars,10),[]);
 assert.throws(()=>movingAverage(bars,0));
 assert.throws(()=>aggregateTicks([],0));
});

test('fit keeps sparse candles narrow on mobile and wide desktop charts',()=>{
 for(const width of [320,700,1900])for(const count of [0,1,2,5,30]){
  const range=fittedRange(count,width);
  assert.ok(width/(range.to-range.from)<=10);
  assert.ok(range.from<=0);
  assert.ok(range.to>=count-1);
 }
});
test('fit includes long histories and leaves room after the newest bar',()=>{
 const range=fittedRange(1800,1200);
 assert.ok(range.from<=0);
 assert.equal(range.to,1803);
 assert.ok(range.to-range.from>=1800);
});
const {exponentialMovingAverage,relativeStrengthIndex,validateDrawings}=require('./chart.js');
const barsFrom=values=>values.map((close,i)=>({time:100+i*10,close}));
test('EMA seeds from complete SMA and applies recursive alpha without future data',()=>{
 const bars=barsFrom([2,4,6,10]);assert.deepEqual(exponentialMovingAverage(bars,3),[{time:120,value:4},{time:130,value:7}]);
 assert.deepEqual(exponentialMovingAverage(bars.slice(0,2),3),[]);
 assert.deepEqual(exponentialMovingAverage(bars,3).slice(0,1),exponentialMovingAverage(bars.slice(0,3),3));
 assert.throws(()=>exponentialMovingAverage(bars,0));
});
test('Wilder RSI needs period+1 observations and handles flat/rising/falling prices',()=>{
 assert.deepEqual(relativeStrengthIndex(barsFrom([1,1,1]),2),[{time:120,value:50}]);
 assert.deepEqual(relativeStrengthIndex(barsFrom([1,2,3]),2),[{time:120,value:100}]);
 assert.deepEqual(relativeStrengthIndex(barsFrom([3,2,1]),2),[{time:120,value:0}]);
 assert.deepEqual(relativeStrengthIndex(barsFrom([1,2]),2),[]);
 const output=relativeStrengthIndex(barsFrom([1,3,2,4]),2);
 assert.ok(Math.abs(output[0].value-66.6666666667)<1e-8);assert.ok(Math.abs(output[1].value-85.7142857143)<1e-8);
 assert.deepEqual(output.slice(0,1),relativeStrengthIndex(barsFrom([1,3,2]),2));assert.throws(()=>relativeStrengthIndex([],0));
});
test('indicator gaps retain observed timestamps and create no intermediate observations',()=>{
 const bars=[{time:10,close:1},{time:100,close:2},{time:1000,close:3}];
 assert.deepEqual(exponentialMovingAverage(bars,2).map(p=>p.time),[100,1000]);
 assert.deepEqual(relativeStrengthIndex(bars,2).map(p=>p.time),[1000]);
});
test('drawing persistence validates prices, timestamps, types and distinct trend anchors',()=>{
 const level={type:'horizontal',points:[{time:100,price:12}]};const trend={type:'trend',points:[{time:100,price:12},{time:200,price:14}]};
 assert.deepEqual(validateDrawings([level,trend,{type:'html',points:[]},{type:'horizontal',points:[{time:100,price:NaN}]},{type:'trend',points:[{time:100,price:12},{time:100,price:14}]}]),[level,trend]);
 assert.deepEqual(validateDrawings({}),[]);assert.equal(validateDrawings(Array(80).fill(level)).length,50);
});

test('custom RSI settings accept 40-level and 40-period choices with valid bounds',()=>{const {validateRsiSettings}=require('./chart.js');assert.equal(validateRsiSettings({period:40,lower:40,upper:70}),true);for(const x of [{period:0,lower:30,upper:70},{period:14.5,lower:30,upper:70},{period:201,lower:30,upper:70},{period:14,lower:80,upper:70},{period:14,lower:40,upper:40},{period:14,lower:NaN,upper:70},{period:14,lower:-1,upper:70},{period:14,lower:30,upper:101}])assert.equal(validateRsiSettings(x),false);});

test('all indicator settings validate custom periods and presentation without accepting invalid values',()=>{
 const {validateIndicatorSettings}=require('./chart.js');
 for(const type of ['sma','ema','rsi']){
  const settings={period:40,color:'#81dfb6',width:3,lower:40,upper:70};
  assert.equal(validateIndicatorSettings(type,settings),true);
  for(const patch of [{period:0},{period:2.5},{period:201},{color:'red'},{width:5}])assert.equal(validateIndicatorSettings(type,{...settings,...patch}),false);
 }
 assert.equal(validateIndicatorSettings('rsi',{period:14,color:'#81dfb6',width:2,lower:80,upper:70}),false);
 assert.equal(validateIndicatorSettings('unknown',{period:40,color:'#81dfb6',width:2}),false);
});
