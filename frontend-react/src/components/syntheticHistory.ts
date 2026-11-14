export type ScenarioBar = { time: number; open: number; high: number; low: number; close: number };
export type InvestingRange = '5m' | '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y';

function seedOf(symbol: string): number {
  let seed = 2166136261;
  for (const char of symbol) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619);
  return seed >>> 0;
}
function random(seed: number): () => number {
  let value = seed;
  return () => { value += 0x6D2B79F5; let next = value; next = Math.imul(next ^ next >>> 15, next | 1); next ^= next + Math.imul(next ^ next >>> 7, next | 61); return ((next ^ next >>> 14) >>> 0) / 4294967296; };
}

/** Generated practice candles. They are deliberately separate from exchange data. */
export function syntheticDailyHistory(symbol: string, lastPrice: number, today = new Date()): ScenarioBar[] {
  if (!Number.isFinite(lastPrice) || lastPrice <= 0) return [];
  const end = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const start = new Date(end); start.setUTCFullYear(start.getUTCFullYear() - 6);
  const next = random(seedOf(symbol)); const raw: ScenarioBar[] = [];
  let price = 100;
  for (let day = start.getTime(); day <= end; day += 86400000) {
    const weekday = new Date(day).getUTCDay(); if (weekday === 0 || weekday === 6) continue;
    const open = price;
    const change = (next() - .5) * .035 + .0002;
    const close = Math.max(1, open * (1 + change));
    const high = Math.max(open, close) * (1 + next() * .008);
    const low = Math.min(open, close) * (1 - next() * .008);
    raw.push({ time: day / 1000, open, high, low, close }); price = close;
  }
  const scale = lastPrice / raw.at(-1)!.close;
  return raw.map(bar => ({ time: bar.time, open: +(bar.open * scale).toFixed(2), high: +(bar.high * scale).toFixed(2), low: +(bar.low * scale).toFixed(2), close: +(bar.close * scale).toFixed(2) }));
}

function startFor(end: number, range: InvestingRange): number {
  const date = new Date(end * 1000);
  const count = range === '1M' ? 1 : range === '3M' ? 3 : range === '6M' ? 6 : range === '1Y' ? 12 : range === '3Y' ? 36 : 60;
  const day = date.getUTCDate(); date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth() - count);
  date.setUTCDate(Math.min(day, new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate()));
  return date.getTime() / 1000;
}
export function scenarioForRange(all: ScenarioBar[], range: InvestingRange): ScenarioBar[] {
  if (!all.length || range === '5m') return [];
  const cutoff = startFor(all.at(-1)!.time, range);
  const daily = all.filter(bar => bar.time >= cutoff).map(bar => ({ ...bar }));
  if (range !== '3Y' && range !== '5Y') return daily;
  const weeks = new Map<number, ScenarioBar>();
  for (const bar of daily) {
    const date = new Date(bar.time * 1000); date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    const time = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) / 1000;
    const old = weeks.get(time);
    weeks.set(time, old ? { time, open: old.open, high: Math.max(old.high, bar.high), low: Math.min(old.low, bar.low), close: bar.close } : { ...bar, time });
  }
  return [...weeks.values()];
}
