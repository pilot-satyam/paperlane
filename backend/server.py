"""Local-only synthetic paper exchange served through Flask; no broker connectivity."""
import argparse
import hashlib
import json
import math
import random
import sqlite3
import threading
import time
import secrets
from datetime import datetime, timezone, timedelta, date
from functools import lru_cache
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from storage import PostgresConnection, configured_database_url, is_postgres_url
from auth import AuthSettings, AuthStore, SESSION_COOKIE, SESSION_SECONDS
from investing import investment_overview

ROOT = Path(__file__).resolve().parent
INITIAL = 1_000_000.0
DEFAULT_DB = ROOT.parents[2] / 'work' / 'paper-trader.sqlite3'
CATALOGUE_PATH = ROOT.parent / 'data' / 'catalogue.json'
MAX_ACTIVE = 100

@lru_cache(maxsize=1)
def option_metadata():
    data = json.loads((ROOT.parent/'data'/'options.json').read_text())
    items = {row[0]: dict(zip(data['columns'], row)) for row in data['rows']}
    grouped = {}
    for item in items.values():
        grouped.setdefault(item['underlying_symbol'], []).append(item)
    return items, grouped, data['coverage']


def option_expired(expiry):
    current = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return expiry < current.date().isoformat() or (expiry == current.date().isoformat() and (current.hour,current.minute) >= (15,30))


def option_years(expiry):
    end = datetime.fromisoformat(expiry).replace(hour=15, minute=30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    return max(0, (end-datetime.now(timezone.utc)).total_seconds()/(365*86400))


def synthetic_option_value(spot, strike, years, volatility, kind):
    """Zero-rate, zero-dividend Black–Scholes illustration; not market calibration."""
    intrinsic = max(0, spot-strike) if kind=='CE' else max(0, strike-spot)
    if years<=0 or volatility<=0:
        return intrinsic
    scale = volatility*math.sqrt(years)
    d1 = (math.log(spot/strike)+.5*scale*scale)/scale
    d2 = d1-scale
    normal = lambda x: .5*(1+math.erf(x/math.sqrt(2)))
    call = spot*normal(d1)-strike*normal(d2)
    return max(intrinsic, call if kind=='CE' else call-spot+strike)


def calibrate_synthetic_volatility(spot, strike, years, price, kind):
    # Anchor legacy demo premiums to avoid an artificial upgrade repricing.
    low, high = .0001, 20.0
    for _ in range(80):
        mid = (low+high)/2
        if synthetic_option_value(spot,strike,years,mid,kind)<price:
            low=mid
        else:
            high=mid
    return (low+high)/2


def now():
    return datetime.now(timezone.utc).isoformat()


def unavailable_technical():
    return dict(status='unavailable', source='SYNTHETIC_SAMPLED_10S', interval_seconds=10,
                as_of=None, last_bar_at=None, last_sample_at=None, last_close=None,
                bar_count=0, contiguous_bar_count=0, gap_count=0, freshness='no_data',
                rsi14=None, sma10=None, ema20=None,
                notes='No technical snapshot was recorded for this fill. Historical indicators are not inferred from current quotes.')


def technical_snapshot(history, as_of):
    """Indicators from completed sampled bars strictly available at the fill timestamp."""
    cutoff = datetime.fromisoformat(as_of.replace('Z','+00:00')).timestamp()
    buckets = {}
    for point in history:
        try:
            moment = datetime.fromisoformat(point['time'].replace('Z','+00:00'))
            if moment.tzinfo is None:
                continue
            timestamp = moment.timestamp()
            value = float(point['value'])
            if not math.isfinite(value) or value <= 0:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        bucket = math.floor(timestamp/10)*10
        if timestamp > cutoff or bucket+10 > cutoff:
            continue  # Neither future samples nor the unfinished current candle can leak in.
        if bucket not in buckets or timestamp >= buckets[bucket][0]:
            buckets[bucket] = (timestamp,value)
    ordered = sorted(buckets)
    gaps = sum((right-left)//10-1 for left,right in zip(ordered,ordered[1:]))
    tail = ordered[-1:]
    for bucket in reversed(ordered[:-1]):
        if tail[0]-bucket != 10:
            break
        tail.insert(0,bucket)
    closes = [buckets[b][1] for b in tail]
    sma = sum(closes[-10:])/10 if len(closes)>=10 else None
    ema = None
    if len(closes)>=20:
        ema = sum(closes[:20])/20
        for close in closes[20:]:
            ema += (close-ema)*2/21
    rsi = None
    if len(closes)>=15:
        changes = [right-left for left,right in zip(closes,closes[1:])]
        gain = sum(max(0,delta) for delta in changes[:14])/14
        loss = sum(max(0,-delta) for delta in changes[:14])/14
        for delta in changes[14:]:
            gain = (gain*13+max(0,delta))/14
            loss = (loss*13+max(0,-delta))/14
        rsi = 50.0 if gain==0 and loss==0 else (100.0 if loss==0 else 100-100/(1+gain/loss))
    last_sample = buckets[ordered[-1]][0] if ordered else None
    def iso(timestamp):
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp is not None else None
    notes = 'Sampled synthetic 10-second bars, not exchange OHLC candles. Only completed bars at or before the fill are used. RSI14 uses Wilder smoothing (15 closes); SMA10 needs 10 and EMA20 needs 20 consecutive closes. Indicators restart after missing intervals; they are context, not trading recommendations.'
    return dict(status='available' if len(closes)>=20 else 'insufficient_history',
                source='SYNTHETIC_SAMPLED_10S', interval_seconds=10, as_of=as_of,
                last_bar_at=iso(ordered[-1]+10) if ordered else None,
                last_sample_at=iso(last_sample), last_close=closes[-1] if closes else None,
                bar_count=len(ordered), contiguous_bar_count=len(closes), gap_count=int(gaps),
                freshness='no_data' if last_sample is None else ('fresh' if cutoff-last_sample<=10 else 'stale'),
                rsi14=rsi, sma10=sma, ema20=ema, notes=notes)


class Exchange:
    def __init__(self, database=DEFAULT_DB, schema='paperlane'):
        self.lock = threading.RLock()
        self.catalogue_data = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
        self.catalogue_by_id = {item['id']: item for item in self.catalogue_data['items']}
        if is_postgres_url(database):
            self.db = PostgresConnection(database, schema)
        else:
            if str(database) != ':memory:':
                Path(database).resolve().parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(database), check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.executescript('''
        CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, cash REAL, realized REAL);
        INSERT OR IGNORE INTO account VALUES (1,1000000,0);
        CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, quantity INTEGER, average_price REAL);
        CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, type TEXT, quantity INTEGER, limit_price REAL, status TEXT, filled_price REAL, fee REAL, created_at TEXT, message TEXT, reservation REAL);
        CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, quantity INTEGER, price REAL, fee REAL, created_at TEXT);
        CREATE TABLE IF NOT EXISTS notes (text TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY, payload TEXT);
        CREATE TABLE IF NOT EXISTS learning_progress (kind TEXT NOT NULL, identifier TEXT NOT NULL, completed_at TEXT NOT NULL, PRIMARY KEY(kind,identifier));
        CREATE TABLE IF NOT EXISTS trade_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, reason TEXT NOT NULL, exit_plan TEXT NOT NULL, max_loss REAL NOT NULL, confidence INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trade_technical (trade_id INTEGER PRIMARY KEY, snapshot TEXT NOT NULL);
            ''')
            order_columns = {row['name'] for row in self.db.execute('PRAGMA table_info(orders)')}
            for name, declaration in (('trigger_price', 'REAL'), ('triggered', 'INTEGER NOT NULL DEFAULT 0'), ('plan_id', 'INTEGER')):
                if name not in order_columns:
                    self.db.execute(f'ALTER TABLE orders ADD COLUMN {name} {declaration}')
            trade_columns = {row['name'] for row in self.db.execute('PRAGMA table_info(trades)')}
            for name, declaration in (('order_id', 'INTEGER'), ('plan_id', 'INTEGER')):
                if name not in trade_columns:
                    self.db.execute(f'ALTER TABLE trades ADD COLUMN {name} {declaration}')
        self.instruments = {}
        self.history = {}
        self.add('NIFTY', 'NIFTY 50 · demo', 'INDEX', 24000)
        for symbol, name, price in [('RELIANCE', 'Reliance Industries', 1450), ('TCS', 'Tata Consultancy Services', 3800), ('HDFCBANK', 'HDFC Bank', 1750), ('INFY', 'Infosys', 1800), ('ICICIBANK', 'ICICI Bank', 1250)]:
            self.add(symbol, name, 'EQUITY', price)
        for strike in range(23700, 24400, 100):
            for typ in ('CE', 'PE'):
                intrinsic = max(0, 24000-strike) if typ == 'CE' else max(0, strike-24000)
                self.add(f'NIFTY-{strike}-{typ}', f'NIFTY {strike} {typ} · demo', 'OPTION', intrinsic+120, underlying='NIFTY', option_type=typ, strike=strike, expiry='2099-12-31', lot_size=50)
        saved = self.db.execute('SELECT payload FROM quotes WHERE id=1').fetchone()
        if saved:
            snapshot = json.loads(saved['payload'])
            self.instruments = snapshot['instruments']
            self.history = snapshot['history']
        for instrument in self.instruments.values():
            if instrument.get('option_catalogue_id') and 'synthetic_volatility' not in instrument:
                spot=self.instruments[instrument['underlying']]['ltp']
                instrument['synthetic_volatility']=calibrate_synthetic_volatility(spot,instrument['strike'],option_years(instrument['expiry']),instrument['ltp'],instrument['option_type'])
                instrument['pricing_model']='SYNTHETIC_BS_ZERO_RATE'
        self.save_quotes()
        self.last_tick = time.monotonic()
        self.updated_at = now()
        # Never retain reservations against an obsolete synthetic quote session.
        self.db.execute("UPDATE orders SET status='CANCELLED', reservation=0, message='Cancelled on server restart: new synthetic session' WHERE status='PENDING'")
        self.db.commit()

    def save_quotes(self):
        self.db.execute('INSERT INTO quotes(id,payload) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (json.dumps(dict(instruments=self.instruments, history=self.history)),))

    def catalogue(self, query='', exchange='ALL', offset=0, limit=40):
        if exchange not in ('ALL', 'NSE', 'BSE'):
            raise ValueError('Exchange must be ALL, NSE or BSE')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError('Offset must be a nonnegative integer')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('Limit must be between 1 and 100')
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError('Search query must contain at most 200 characters')
        terms = query.casefold().split()
        matches = [item for item in self.catalogue_data['items']
                   if (exchange == 'ALL' or item['exchange'] == exchange)
                   and all(term in ' '.join(str(item[key]) for key in ('id', 'trading_symbol', 'name', 'series', 'isin')).casefold() for term in terms)]
        return dict(items=matches[offset:offset+limit], total=len(matches), offset=offset,
                    limit=limit, coverage=self.catalogue_data['coverage'])

    @staticmethod
    def quantize(price, tick):
        step = Decimal(str(tick))
        return float(max(step, (Decimal(str(price))/step).quantize(Decimal('1'), rounding=ROUND_HALF_UP)*step))

    def activate(self, data):
        identifier = data.get('id') if isinstance(data, dict) else None
        if not isinstance(identifier, str) or identifier not in self.catalogue_by_id:
            raise ValueError('Choose a valid catalogue instrument ID')
        item = self.catalogue_by_id[identifier]
        if not item['can_simulate']:
            raise ValueError(item['restriction'])
        with self.lock, self.db:
            symbol = identifier
            # Keep historic account keys for the original NSE demo stocks only.
            if item['exchange'] == 'NSE' and item['series'] == 'EQ' and item['trading_symbol'] in ('RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK'):
                symbol = item['trading_symbol']
            if symbol not in self.instruments:
                if len(self.instruments) >= MAX_ACTIVE:
                    raise ValueError(f'Active instrument limit reached ({MAX_ACTIVE}); catalogue search remains available')
                seed = int.from_bytes(hashlib.sha256(identifier.encode()).digest()[:8], 'big')
                price = self.quantize(25+(seed % 497500)/100, item['tick_size'])
                self.add(symbol, f"{item['trading_symbol']} · {item['name']} ({item['exchange']})", 'EQUITY', price)
            instrument = self.instruments[symbol]
            instrument.update({key: item[key] for key in ('exchange', 'series', 'isin', 'lot_size', 'tick_size', 'buy_allowed', 'sell_allowed')})
            instrument.update(catalogue_id=identifier, display_symbol=f"{item['trading_symbol']} · {item['exchange']}",
                              price_source='SYNTHETIC_ARBITRARY',
                              price_note='Arbitrary synthetic simulation price; not a current market quote or valuation.')
            # Current last-price/history stays intact for legacy positions; new bid/ask obey imported ticks.
            tick = item['tick_size']
            instrument['bid'] = self.quantize(max(tick, instrument['ltp']-max(tick, instrument['ltp']*.0005)), tick)
            instrument['ask'] = self.quantize(instrument['ltp']+max(tick, instrument['ltp']*.0005), tick)
            self.save_quotes()
            return dict(symbol=symbol, instrument={key: value for key, value in instrument.items() if key != 'base'})

    def option_underlying(self, symbol):
        if not isinstance(symbol, str):
            raise ValueError('Select a cash underlying')
        active = self.instruments.get(symbol)
        if active and active['kind'] == 'OPTION':
            return self.option_underlying(active['underlying'])
        if symbol == 'NIFTY':
            return dict(symbol='NIFTY', display_symbol='NIFTY · NSE', ltp=self.instruments['NIFTY']['ltp'], trading_symbol='NIFTY', catalogue_id=None)
        item = self.catalogue_by_id.get((active or {}).get('catalogue_id', symbol))
        if item is None and active and active['kind'] == 'EQUITY':
            item = next((i for i in self.catalogue_data['items'] if i['exchange']=='NSE' and i['series']=='EQ' and i['trading_symbol']==symbol), None)
        if item is None:
            raise ValueError('No cash-underlying metadata found for this selection')
        if item['exchange'] == 'BSE':
            matches = [i for i in self.catalogue_data['items'] if item['isin'] and i['isin']==item['isin'] and i['exchange']=='NSE' and i['series']=='EQ']
            if len(matches) != 1:
                return dict(symbol=symbol, display_symbol=f"{item['trading_symbol']} · BSE", ltp=(active or {}).get('ltp'), trading_symbol=None, catalogue_id=None)
            item = matches[0]
        key = item['trading_symbol'] if item['trading_symbol'] in ('RELIANCE','TCS','HDFCBANK','INFY','ICICIBANK') else item['id']
        canonical = self.instruments.get(key)
        seed = int.from_bytes(hashlib.sha256(item['id'].encode()).digest()[:8], 'big')
        price = canonical['ltp'] if canonical else self.quantize(25+(seed%497500)/100, item['tick_size'] or .01)
        if not canonical:
            _, grouped, _ = option_metadata()
            listed = [c for c in grouped.get(item['trading_symbol'],[]) if not option_expired(c['expiry']) and not c['is_reserved']]
            if listed:
                nearest = min(c['expiry'] for c in listed)
                strikes = sorted({c['strike'] for c in listed if c['expiry']==nearest})
                price = self.quantize((strikes[(len(strikes)-1)//2]+strikes[len(strikes)//2])/2,item['tick_size'] or .01)
        return dict(symbol=key, display_symbol=f"{item['trading_symbol']} · NSE", ltp=price, trading_symbol=item['trading_symbol'], catalogue_id=item['id'])

    def option_quote(self, contract, spot):
        volatility=contract.get('synthetic_volatility', .35)
        value=synthetic_option_value(spot,contract['strike'],option_years(contract['expiry']),volatility,contract['option_type'])
        price = self.quantize(value,contract['tick_size'])
        spread = max(contract['tick_size'],price*.001)
        return dict(ltp=price,bid=self.quantize(price-spread,contract['tick_size']),ask=self.quantize(price+spread,contract['tick_size']))

    def option_chain(self, symbol, expiry=None):
        with self.lock:
            underlying = self.option_underlying(symbol)
            _, grouped, coverage = option_metadata()
            contracts = grouped.get(underlying['trading_symbol'], [])
            expiries = sorted({c['expiry'] for c in contracts if not option_expired(c['expiry'])})
            if expiry and expiry not in expiries:
                raise ValueError('Selected expiry is expired or absent from this underlying snapshot')
            chosen = expiry or (expiries[0] if expiries else None)
            items = []
            for contract in contracts:
                if contract['expiry'] != chosen:
                    continue
                restriction = 'Provider snapshot marks this contract reserved; activation unavailable.' if contract['is_reserved'] else ''
                if not contract['buy_allowed'] and not contract['sell_allowed']:
                    restriction = 'Provider snapshot disables dealing in this contract.'
                active = self.instruments.get(contract['id'])
                quote = {k:active[k] for k in ('ltp','bid','ask')} if active else self.option_quote(contract, underlying['ltp'])
                items.append(dict(**contract, symbol=contract['id'], **quote, can_trade=not bool(restriction), restriction=restriction))
            notes = 'Snapshot contract metadata; all premiums and underlying quotes are synthetic, not current valuations. Chain uses the canonical NSE underlying; a selected BSE cash quote can differ. New inactive NSE underlyings start at the median nearby listed strike for practice, not a market price; existing prices are preserved. Expiry settlement is not implemented. Reserved contracts are view-only.'
            if not items:
                notes = 'No unexpired NSE option contracts found for this cash underlying in the supplied snapshot. No unrelated chain is substituted.'
            return dict(mode='SIMULATED',underlying=underlying,expiries=expiries,expiry=chosen,contracts=sorted(items,key=lambda c:(c['strike'],c['option_type'])),notes=notes,coverage=coverage)

    def activate_option(self, data):
        identifier = data.get('id') if isinstance(data,dict) else None
        items, _, _ = option_metadata()
        if not isinstance(identifier,str) or identifier not in items:
            raise ValueError('Choose a valid snapshot option contract')
        contract = items[identifier]
        if option_expired(contract['expiry']):
            raise ValueError('Contract expired; settlement is not implemented')
        if contract['is_reserved'] or not (contract['buy_allowed'] or contract['sell_allowed']):
            raise ValueError('Provider snapshot marks contract reserved or unavailable for dealing')
        with self.lock, self.db:
            if identifier in self.instruments:
                return dict(symbol=identifier,instrument={k:v for k,v in self.instruments[identifier].items() if k!='base'})
            token = f"NSE:{contract['underlying_token']}"
            underlying = self.option_underlying('NIFTY' if contract['underlying_symbol']=='NIFTY' else token)
            needed = 1 + int(underlying['symbol'] not in self.instruments)
            if len(self.instruments)+needed > MAX_ACTIVE:
                raise ValueError(f'Active instrument limit reached ({MAX_ACTIVE}); cannot activate option and underlying')
            if underlying['catalogue_id']:
                already_active = underlying['symbol'] in self.instruments
                self.activate({'id':underlying['catalogue_id']})
                if not already_active:
                    cash = self.instruments[underlying['symbol']]
                    cash.update(ltp=underlying['ltp'],base=underlying['ltp'])
                    tick=cash['tick_size']
                    cash['bid']=self.quantize(cash['ltp']-max(tick,cash['ltp']*.0005),tick)
                    cash['ask']=self.quantize(cash['ltp']+max(tick,cash['ltp']*.0005),tick)
                    cash['price_note']='Synthetic practice baseline anchored to median listed strike; not a current price or valuation.'
                    self.history[underlying['symbol']]=[dict(time=now(),value=cash['ltp'])]
            quote = self.option_quote(contract,self.instruments[underlying['symbol']]['ltp'])
            self.add(identifier,contract['trading_symbol']+' · NSE', 'OPTION',quote['ltp'],underlying=underlying['symbol'],option_type=contract['option_type'],strike=contract['strike'],expiry=contract['expiry'],lot_size=contract['lot_size'])
            instrument=self.instruments[identifier]
            instrument.update(quote)
            instrument.update(synthetic_volatility=.35,pricing_model='SYNTHETIC_BS_ZERO_RATE')
            instrument.update(tick_size=contract['tick_size'],buy_allowed=contract['buy_allowed'],sell_allowed=contract['sell_allowed'],option_catalogue_id=identifier,contract_id=identifier,display_symbol=contract['trading_symbol']+' · NSE',exchange='NSE',price_source='SYNTHETIC_ARBITRARY',price_note='Synthetic premium; not a current option quote or valuation.')
            self.save_quotes()
            return dict(symbol=identifier,instrument={k:v for k,v in instrument.items() if k!='base'})

    def reduces_exposure(self, symbol, side, quantity):
        old = self.positions().get(symbol, {}).get('quantity', 0)
        delta = quantity if side == 'BUY' else -quantity
        return old*delta < 0 and quantity <= abs(old)

    def add(self, symbol, name, kind, price, **fields):
        self.instruments[symbol] = dict(symbol=symbol, name=name, kind=kind, underlying=None, option_type=None, strike=None, expiry=None, lot_size=1, ltp=price, bid=round(price*.9995, 2), ask=round(price*1.0005, 2), change_pct=0, **{})
        self.instruments[symbol].update(fields)
        self.instruments[symbol]['base'] = price
        self.history[symbol] = [dict(time=now(), value=price)]

    def positions(self):
        return {r['symbol']: dict(r) for r in self.db.execute('SELECT * FROM positions')}

    def account(self, positions=None, cash=None):
        row = self.db.execute('SELECT * FROM account WHERE id=1').fetchone()
        cash = row['cash'] if cash is None else cash
        positions = self.positions() if positions is None else positions
        value = liability = margin = unrealized = 0.0
        for symbol, p in positions.items():
            i = self.instruments[symbol]
            q, price = p['quantity'], i['ltp']
            value += q*price
            unrealized += q*(price-p['average_price'])
            if q < 0:
                liability += -q*price
                rate = self.instruments[i['underlying']]['ltp']*.3 if i['kind'] == 'OPTION' else price
                margin += -q*rate
        reserved = self.db.execute("SELECT COALESCE(SUM(reservation),0) AS reserved FROM orders WHERE status='PENDING'").fetchone()['reserved']
        return dict(initial_balance=INITIAL, cash=cash, equity=cash+value, available_margin=cash-liability-margin-reserved, used_margin=margin+reserved, realized_pnl=row['realized'], unrealized_pnl=unrealized)

    @staticmethod
    def fee(price, quantity):
        return round(price*quantity*.0005, 2)  # Illustrative 0.05%, not actual tax/brokerage.

    def project(self, symbol, side, quantity, price):
        positions = self.positions()
        old = positions.get(symbol, dict(quantity=0, average_price=0))
        q, avg = old['quantity'], old['average_price']
        delta = quantity if side == 'BUY' else -quantity
        new = q+delta
        realized = min(abs(q), abs(delta))*(price-avg)*(1 if q > 0 else -1) if q*delta < 0 else 0
        newavg = (abs(q)*avg+abs(delta)*price)/abs(new) if q*delta >= 0 else (avg if new*q > 0 else price)
        positions[symbol] = dict(symbol=symbol, quantity=new, average_price=newavg if new else 0)
        fee = self.fee(price, quantity)
        cash = self.db.execute('SELECT cash FROM account WHERE id=1').fetchone()['cash']-delta*price-fee
        return positions, cash, realized-fee, fee

    def order_dict(self, oid):
        out = dict(self.db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone())
        out.pop('reservation', None)
        return out

    def selected_plan(self, plan_id, symbol):
        if plan_id is None:
            return None
        if isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0:
            raise ValueError('Choose a valid saved plan')
        plan = self.db.execute('SELECT * FROM trade_plans WHERE id=?', (plan_id,)).fetchone()
        if not plan or plan['symbol'] != symbol:
            raise ValueError('The saved plan must match this instrument')
        return dict(plan)

    def order_preview(self, data):
        """A quote-based teaching estimate, not a fill or a guaranteed loss limit."""
        if not isinstance(data, dict):
            raise ValueError('Expected an order preview object')
        symbol, side, quantity = (data.get(key) for key in ('symbol', 'side', 'quantity'))
        with self.lock:
            i = self.instruments.get(symbol) if isinstance(symbol, str) else None
            if not i or i['kind'] == 'INDEX':
                raise ValueError('Choose a tradable demo stock or option')
            if side not in ('BUY', 'SELL') or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0 or quantity > 10_000_000 or quantity % i['lot_size']:
                raise ValueError('Choose BUY or SELL and a valid lot quantity')
            plan = self.selected_plan(data.get('plan_id'), symbol)
            price = i['ask'] if side == 'BUY' else i['bid']
            spread = max(0, i['ask'] - i['bid'])
            return dict(symbol=symbol,side=side,quantity=quantity,quote_price=price,
                        estimated_trade_value=round(price*quantity,2),
                        estimated_entry_fee=self.fee(price,quantity),
                        estimated_full_spread_cost=round(spread*quantity,2),
                        plan_max_loss=plan['max_loss'] if plan else None,
                        plan_id=plan['id'] if plan else None,
                        explanation='Spread cost assumes an immediate buy and sell at the displayed quotes. Fees are illustrative. Planned loss is your budget, not a guaranteed maximum. Real fills and losses can differ.')

    def submit(self, data):
        with self.lock:
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            symbol, side, typ, q = (data.get(k) for k in ('symbol', 'side', 'type', 'quantity'))
            if not isinstance(symbol, str) or symbol not in self.instruments or self.instruments[symbol]['kind'] == 'INDEX':
                raise ValueError('Choose a tradable demo stock or option')
            if self.instruments[symbol]['kind']=='OPTION' and option_expired(self.instruments[symbol]['expiry']):
                raise ValueError('Contract expired; orders disabled because settlement is not implemented')
            if side not in ('BUY', 'SELL') or typ not in ('MARKET', 'LIMIT', 'STOP_LIMIT'):
                raise ValueError('Invalid order side or type')
            if self.instruments[symbol].get('buy_allowed' if side == 'BUY' else 'sell_allowed') is False:
                raise ValueError(f'{side} disabled by the imported provider metadata snapshot')
            if isinstance(q, bool) or not isinstance(q, int) or q <= 0 or q > 10_000_000 or q % self.instruments[symbol]['lot_size']:
                raise ValueError('Quantity must be a positive whole number and a valid lot multiple')
            limit = data.get('limit_price') if typ in ('LIMIT', 'STOP_LIMIT') else None
            if typ in ('LIMIT', 'STOP_LIMIT') and (isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit <= 0 or limit > 10_000_000):
                raise ValueError('Limit price must be a finite positive number')
            tick = self.instruments[symbol].get('tick_size')
            if typ in ('LIMIT', 'STOP_LIMIT') and tick and Decimal(str(limit)) % Decimal(str(tick)) != 0:
                raise ValueError(f'Limit price must be a multiple of the imported tick size {tick}')
            trigger = data.get('trigger_price') if typ == 'STOP_LIMIT' else None
            if typ == 'STOP_LIMIT':
                if isinstance(trigger, bool) or not isinstance(trigger, (int, float)) or not math.isfinite(trigger) or not 0 < trigger <= 10_000_000:
                    raise ValueError('Trigger price must be a finite positive number')
                if tick and Decimal(str(trigger)) % Decimal(str(tick)) != 0:
                    raise ValueError(f'Trigger price must be a multiple of the imported tick size {tick}')
                if (side == 'BUY' and limit < trigger) or (side == 'SELL' and limit > trigger):
                    raise ValueError('Buy stop limit must be at or above trigger; sell stop limit must be at or below trigger')
            if time.monotonic()-self.last_tick > 10:
                raise ValueError('Quotes are stale; trading is paused')
            # Serialize same-symbol open orders so closing quantities cannot be pledged twice.
            if self.db.execute("SELECT 1 FROM orders WHERE symbol=? AND status='PENDING'", (symbol,)).fetchone():
                raise ValueError('Cancel the pending order for this instrument before placing another')
            i = self.instruments[symbol]
            plan = self.selected_plan(data.get('plan_id'), symbol)
            price = i['ask'] if side == 'BUY' else i['bid']
            triggered = typ == 'STOP_LIMIT' and (i['ltp'] >= trigger if side == 'BUY' else i['ltp'] <= trigger)
            matches = (typ != 'STOP_LIMIT' or triggered) and (typ == 'MARKET' or (price <= limit if side == 'BUY' else price >= limit))
            # Do not use an optimistic distant sell limit to finance its own margin.
            estimate = price if matches or side == 'SELL' else limit
            projected, cash, _, _ = self.project(symbol, side, q, estimate)
            current = self.account()['available_margin']
            after = self.account(projected, cash)['available_margin']
            reservation = max(0, current-after)
            status = 'PENDING' if after >= -0.001 or self.reduces_exposure(symbol, side, q) else 'REJECTED'
            message = 'Waiting for matching bid/ask' if status == 'PENDING' else 'Insufficient virtual funds or estimated short margin'
            if status == 'PENDING' and typ == 'STOP_LIMIT' and not triggered:
                message = 'Waiting for stop trigger; funds/margin reserved'
            with self.db:
                sql = 'INSERT INTO orders(symbol,side,type,quantity,limit_price,status,filled_price,fee,created_at,message,reservation,trigger_price,triggered,plan_id) VALUES (?,?,?,?,?,?,NULL,0,?,?,?,?,?,?)'
                cur = self.db.execute(sql + (' RETURNING id' if getattr(self.db, 'is_postgres', False) else ''), (symbol, side, typ, q, limit, status, now(), message, reservation if status == 'PENDING' else 0, trigger, int(triggered), plan['id'] if plan else None))
                oid = cur.fetchone()['id'] if getattr(self.db, 'is_postgres', False) else cur.lastrowid
                if matches and status == 'PENDING':
                    self.fill(oid, price)
            return self.order_dict(oid)

    def fill(self, oid, price):
        o = self.order_dict(oid)
        self.db.execute('UPDATE orders SET reservation=0 WHERE id=?', (oid,))
        positions, cash, realized, fee = self.project(o['symbol'], o['side'], o['quantity'], price)
        if self.account(positions, cash)['available_margin'] < -.001 and not self.reduces_exposure(o['symbol'], o['side'], o['quantity']):
            self.db.execute("UPDATE orders SET status='REJECTED', message='Insufficient funds at execution' WHERE id=?", (oid,))
            return
        p = positions[o['symbol']]
        self.db.execute('INSERT INTO positions(symbol,quantity,average_price) VALUES (?,?,?) ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity, average_price=excluded.average_price', (o['symbol'], p['quantity'], p['average_price']))
        self.db.execute('DELETE FROM positions WHERE quantity=0')
        self.db.execute('UPDATE account SET cash=?, realized=realized+? WHERE id=1', (cash, realized))
        self.db.execute("UPDATE orders SET status='FILLED', filled_price=?, fee=?, message='Synthetic bid/ask fill' WHERE id=?", (price, fee, oid))
        filled_at = now()
        trade_sql = 'INSERT INTO trades(symbol,side,quantity,price,fee,created_at,order_id,plan_id) VALUES (?,?,?,?,?,?,?,?)'
        trade = self.db.execute(trade_sql + (' RETURNING id' if getattr(self.db, 'is_postgres', False) else ''), (o['symbol'], o['side'], o['quantity'], price, fee, filled_at, oid, o['plan_id']))
        snapshot = technical_snapshot(self.history.get(o['symbol'],[]),filled_at)
        trade_id = trade.fetchone()['id'] if getattr(self.db, 'is_postgres', False) else trade.lastrowid
        self.db.execute('INSERT INTO trade_technical(trade_id,snapshot) VALUES (?,?)',(trade_id,json.dumps(snapshot,allow_nan=False)))

    def cancel(self, oid):
        with self.lock, self.db:
            row = self.db.execute('SELECT status FROM orders WHERE id=?', (oid,)).fetchone()
            if not row or row['status'] != 'PENDING':
                raise ValueError('Only an existing pending order can be cancelled')
            self.db.execute("UPDATE orders SET status='CANCELLED', reservation=0, message='Cancelled by user' WHERE id=?", (oid,))
            return self.order_dict(oid)

    def tick(self):
        with self.lock, self.db:
            timestamp = now()
            for i in self.instruments.values():
                if i['kind']=='OPTION' and option_expired(i['expiry']):
                    continue
                price = max(.05, i['ltp']*(1+random.gauss(0, .00035)))
                if i['kind'] == 'OPTION':
                    spot = self.instruments[i['underlying']]['ltp']
                    intrinsic = max(0, spot-i['strike']) if i['option_type'] == 'CE' else max(0, i['strike']-spot)
                    # Correlated illustrative premiums, not an options pricing model.
                    price = max(.05, intrinsic + 120 + random.gauss(0, .6))
                    if i.get('option_catalogue_id'):
                        price = self.option_quote(i, spot)['ltp']
                i.update(ltp=round(price, 2), bid=round(max(.05, price-max(.05, price*.0005)), 2), ask=round(price+max(.05, price*.0005), 2), change_pct=round((price/i['base']-1)*100, 2))
                if i.get('tick_size'):
                    tick = i['tick_size']
                    i['ltp'] = self.quantize(price, tick)
                    i['bid'] = self.quantize(max(tick, i['ltp']-max(tick, price*.0005)), tick)
                    i['ask'] = self.quantize(i['ltp']+max(tick, price*.0005), tick)
                    i['change_pct'] = round((i['ltp']/i['base']-1)*100, 2)
                h = self.history[i['symbol']]
                h.append(dict(time=timestamp, value=i['ltp']))
                del h[:-1800]
            self.last_tick, self.updated_at = time.monotonic(), timestamp
            self.save_quotes()
            for row in self.db.execute("SELECT * FROM orders WHERE status='PENDING' ORDER BY id").fetchall():
                i = self.instruments[row['symbol']]
                if i['kind']=='OPTION' and option_expired(i['expiry']):
                    self.db.execute("UPDATE orders SET status='CANCELLED', reservation=0, message='Contract expired; settlement not implemented' WHERE id=?",(row['id'],))
                    continue
                if row['type'] == 'STOP_LIMIT' and not row['triggered']:
                    triggered = i['ltp'] >= row['trigger_price'] if row['side'] == 'BUY' else i['ltp'] <= row['trigger_price']
                    if not triggered:
                        continue
                    self.db.execute("UPDATE orders SET triggered=1, message='Stop triggered; waiting for matching bid/ask' WHERE id=?", (row['id'],))
                price = i['ask'] if row['side'] == 'BUY' else i['bid']
                if price <= row['limit_price'] if row['side'] == 'BUY' else price >= row['limit_price']:
                    self.fill(row['id'], price)

    def investing_state(self):
        """Small consistent snapshot without serializing orders and option history."""
        with self.lock:
            equities = {symbol: instrument for symbol, instrument in self.instruments.items()
                        if instrument['kind'] == 'EQUITY'}
            return dict(updated_at=self.updated_at, instruments=[dict(item) for item in equities.values()],
                        positions=[dict(row) for row in self.db.execute('SELECT * FROM positions')
                                   if row['symbol'] in equities],
                        history={symbol: list(points) for symbol, points in self.history.items()
                                 if symbol in equities})

    def state(self, history_after=None):
        with self.lock:
            ps = []
            for symbol, p in self.positions().items():
                price = self.instruments[symbol]['ltp']
                ps.append(dict(**p, ltp=price, unrealized_pnl=p['quantity']*(price-p['average_price'])))
            cursor = max((h[-1]['time'] for h in self.history.values() if h), default=self.updated_at)
            # A client that missed the retention window needs a fresh chart snapshot.
            snapshot = (history_after is None or history_after > cursor or
                        any(len(h) >= 1800 and history_after < h[0]['time']
                            for h in self.history.values() if h))
            history = ({s: [dict(point) for point in h] for s, h in self.history.items()}
                       if snapshot else
                       {s: [dict(point) for point in reversed(new_points)]
                        for s, h in self.history.items()
                        if (new_points := list(self._history_since_reversed(h, history_after)))})
            return dict(mode='SIMULATED', market_status='DEMO SESSION' if time.monotonic()-self.last_tick <= 10 else 'STALE — TRADING PAUSED', updated_at=self.updated_at, account=self.account(), instruments=[{**{k:v for k,v in i.items() if k != 'base'}, 'practice_reference_price': i.get('base', i['ltp'])} for i in self.instruments.values()], positions=ps, orders=[self.order_dict(r['id']) for r in self.db.execute('SELECT id FROM orders ORDER BY id DESC LIMIT 300')], trades=[dict(r) for r in self.db.execute('SELECT * FROM trades ORDER BY id DESC LIMIT 300')], history=history, history_mode='snapshot' if snapshot else 'delta', history_cursor=cursor)

    @staticmethod
    def _history_since_reversed(points, cursor):
        for point in reversed(points):
            if point['time'] <= cursor:
                break
            yield point

    def report(self):
        """Reconstruct average-cost closes and prorated fees without changing the ledger."""
        with self.lock:
            fills = [dict(row) for row in self.db.execute('SELECT * FROM trades ORDER BY id')]
            snapshots = {row['trade_id']:json.loads(row['snapshot']) for row in self.db.execute('SELECT * FROM trade_technical')}
            plans = {row['id']:dict(row) for row in self.db.execute('SELECT * FROM trade_plans')}
        positions, closed = {}, []
        gross_total = fee_total = 0.0
        for fill in fills:
            symbol, quantity, price, fee = (fill[k] for k in ('symbol', 'quantity', 'price', 'fee'))
            delta = quantity if fill['side'] == 'BUY' else -quantity
            snapshot = snapshots.get(fill['id'],unavailable_technical())
            position = positions.get(symbol, dict(quantity=0, average_price=0, entry_fees=0, entry_at=None, entry_technical=unavailable_technical(), plan_id=None, plan_mixed=False))
            old_quantity = position['quantity']
            fee_total += fee
            if old_quantity * delta < 0:
                closing = min(abs(old_quantity), quantity)
                entry_fees = position['entry_fees'] * closing / abs(old_quantity)
                exit_fees = fee * closing / quantity
                direction = 'LONG' if old_quantity > 0 else 'SHORT'
                gross = closing * (price-position['average_price']) * (1 if old_quantity > 0 else -1)
                gross_total += gross
                closed.append(dict(symbol=symbol, direction=direction, quantity=closing,
                                   entry_price=position['average_price'], exit_price=price,
                                   entry_at=position['entry_at'], exit_at=fill['created_at'],
                                   gross_pnl=gross, fees=entry_fees+exit_fees,
                                   net_pnl=gross-entry_fees-exit_fees,
                                   technical=dict(entry=position['entry_technical'],exit=snapshot),
                                   entry_trade_id=position.get('entry_trade_id'),exit_trade_id=fill['id'],
                                   plan=plans.get(position['plan_id']) if position.get('plan_id') else None,
                                   plan_link_status='ambiguous' if position.get('plan_mixed') else ('recorded' if position.get('plan_id') else 'unavailable')))
                fill['effect'] = f'Closed {closing} {direction.lower()} units'
                remaining = old_quantity + delta
                if quantity > abs(old_quantity):
                    position = dict(quantity=remaining, average_price=price,
                                    entry_fees=fee-exit_fees, entry_at=fill['created_at'],entry_technical=snapshot,plan_id=fill.get('plan_id'),plan_mixed=False,entry_trade_id=fill['id'])
                    fill['effect'] += f" and opened {abs(remaining)} {'long' if remaining > 0 else 'short'} units"
                else:
                    position['quantity'] = remaining
                    position['entry_fees'] -= entry_fees
            else:
                remaining = old_quantity + delta
                position['average_price'] = (abs(old_quantity)*position['average_price']+quantity*price)/abs(remaining)
                position['quantity'] = remaining
                position['entry_fees'] += fee
                if old_quantity == 0:
                    position['entry_at'] = fill['created_at']
                    position['entry_technical'] = snapshot
                    position['entry_trade_id'] = fill['id']
                    position['plan_id'] = fill.get('plan_id')
                if old_quantity and position.get('plan_id') != fill.get('plan_id'):
                    position['plan_id'] = None  # Mixed entries cannot be assigned to one plan.
                    position['plan_mixed'] = True
                fill['effect'] = f"{'Added' if old_quantity else 'Opened'} {quantity} {'long' if delta > 0 else 'short'} units"
            if position['quantity']:
                positions[symbol] = position
            else:
                positions.pop(symbol, None)
        return dict(summary=dict(gross_pnl=gross_total, total_fees=fee_total,
                                 net_realized_pnl=gross_total-fee_total,
                                 closed_net_pnl=sum(row['net_pnl'] for row in closed),
                                 open_entry_fees=sum(p['entry_fees'] for p in positions.values()),
                                 fill_count=len(fills), open_position_count=len(positions)),
                    closed=list(reversed(closed)), fills=list(reversed(fills)))

    def learning(self, data=None):
        """Personal learning records persist independently of resetting the virtual account."""
        with self.lock, self.db:
            if data is not None:
                if not isinstance(data, dict) or not data or set(data)-{'lesson_id','exercise_id'}:
                    raise ValueError('Provide lesson_id and/or exercise_id')
                allowed = {'lesson_id': {'basics','orders','pnl','risk','options','review','candles','levels','averages','rsi','sizing','expectancy','liquidity','moneyness','greeks','routine','futures','option_side','option_chain','option_payoff','option_risks','option_execution','premium_parts','theta_decay','delta_gamma','iv_vega','strike_choice','premium_story','seller_theta_risk','greek_checklist','invest_goal','invest_share','invest_compound','invest_statements','invest_valuation','invest_research','invest_diversify','invest_chart','invest_multibagger','invest_review'},
                           'exercise_id': {'limit','cancel','roundtrip','journal','candles','indicator','levels','costs'}}
                # Validate all inputs before storing any progress.
                for key, value in data.items():
                    if not isinstance(value,str) or value not in allowed[key]:
                        raise ValueError(f'Unknown {key}')
                for key, value in data.items():
                    self.db.execute('INSERT INTO learning_progress(kind,identifier,completed_at) VALUES (?,?,?) ON CONFLICT(kind,identifier) DO NOTHING',
                                    ('lesson' if key=='lesson_id' else 'exercise',value,now()))
            progress = self.db.execute('SELECT kind,identifier FROM learning_progress ORDER BY completed_at,identifier').fetchall()
            return dict(completed=[r['identifier'] for r in progress if r['kind']=='lesson'],
                        exercises=[r['identifier'] for r in progress if r['kind']=='exercise'],
                        plans=[dict(r) for r in self.db.execute('SELECT * FROM trade_plans ORDER BY id DESC')])

    def trade_plan(self, data):
        if not isinstance(data,dict) or set(data) != {'symbol','reason','exit_plan','max_loss','confidence'}:
            raise ValueError('Provide symbol, reason, exit_plan, max_loss and confidence')
        symbol,reason,exit_plan = (data[k] for k in ('symbol','reason','exit_plan'))
        if not isinstance(symbol,str) or not symbol.strip() or len(symbol)>100:
            raise ValueError('Symbol must contain 1–100 characters')
        if not isinstance(reason,str) or not 1 <= len(reason.strip()) <= 2000:
            raise ValueError('Trade reason must contain 1–2000 characters')
        if not isinstance(exit_plan,str) or not 1 <= len(exit_plan.strip()) <= 2000:
            raise ValueError('Exit plan must contain 1–2000 characters')
        max_loss, confidence = data['max_loss'],data['confidence']
        if isinstance(max_loss,bool) or not isinstance(max_loss,(int,float)) or not math.isfinite(max_loss) or max_loss<=0:
            raise ValueError('Maximum loss must be a finite positive amount')
        if isinstance(confidence,bool) or not isinstance(confidence,int) or not 1<=confidence<=5:
            raise ValueError('Confidence must be a whole number from 1 to 5')
        with self.lock, self.db:
            self.db.execute('INSERT INTO trade_plans(symbol,reason,exit_plan,max_loss,confidence,created_at) VALUES (?,?,?,?,?,?)',
                            (symbol.strip(),reason.strip(),exit_plan.strip(),max_loss,confidence,now()))
            return self.learning()

    def journal(self, data=None):
        with self.lock, self.db:
            if data is not None:
                value = data.get('text') if isinstance(data, dict) else None
                if not isinstance(value, str) or not value.strip() or len(value) > 5000:
                    raise ValueError('Journal text must contain 1–5000 characters')
                self.db.execute('INSERT INTO notes VALUES (?,?)', (value.strip(), now()))
            return dict(notes=[dict(r) for r in self.db.execute('SELECT * FROM notes ORDER BY created_at DESC')])

    def reset(self):
        with self.lock, self.db:
            for table in ('positions', 'orders', 'trades', 'notes', 'trade_technical'):
                self.db.execute(f'DELETE FROM {table}')
            self.db.execute('UPDATE account SET cash=?,realized=0 WHERE id=1', (INITIAL,))
            return dict(ok=True)


class ExchangeManager:
    """Keep an independently scoped synthetic account for each validated user."""

    def __init__(self, database):
        if not is_postgres_url(database):
            raise RuntimeError('Authenticated accounts require PostgreSQL')
        self.database = database
        self.lock = threading.RLock()
        self.accounts = {}

    def get(self, user):
        schema = user['account_schema']
        with self.lock:
            if schema not in self.accounts:
                self.accounts[schema] = Exchange(self.database, schema=schema)
            return self.accounts[schema]

    def tick(self):
        with self.lock:
            accounts = list(self.accounts.values())
        for account in accounts:
            account.tick()


def create_app(exchange=None, port=8000, frontend_root=None, auth=None,
               allow_unauthenticated_for_tests=False):
    """Create the HTTP app without starting the synthetic quote thread."""
    if exchange is None:
        database = configured_database_url()
        if not database:
            raise RuntimeError('Configure PostgreSQL in DATABASE_URL or .env.local before starting the app')
        exchange = ExchangeManager(database)
        auth = auth or AuthStore(database, AuthSettings.from_environment())
    if auth is None and not allow_unauthenticated_for_tests:
        raise RuntimeError('Authentication is required. Use explicit test mode only in tests.')
    react_build = ROOT.parent / 'frontend-react' / 'dist'
    frontend_root = Path(frontend_root or (react_build if (react_build / 'index.html').exists() else ROOT.parent / 'frontend'))
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 16384
    remote = None
    if auth is not None:
        from authlib.integrations.flask_client import OAuth
        settings = auth.settings
        trusted_hosts = [urlparse(settings.base_url).hostname]
        if trusted_hosts[0] in ('127.0.0.1', 'localhost'):
            trusted_hosts = ['127.0.0.1', 'localhost']
        app.config.update(SECRET_KEY=settings.secret_key,
                          SESSION_COOKIE_NAME='paperlane_oidc',
                          SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SECURE=settings.secure_cookies,
                          SESSION_COOKIE_SAMESITE='Lax',
                          PERMANENT_SESSION_LIFETIME=600,
                          TRUSTED_HOSTS=trusted_hosts)
        remote = OAuth(app).register(
            'identity', client_id=settings.client_id, client_secret=settings.client_secret,
            server_metadata_url=settings.issuer + '/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid profile email', 'code_challenge_method': 'S256'})

    def current_exchange():
        return exchange.get(g.user) if auth is not None else exchange

    @app.after_request
    def no_store_api(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    def invalid_input(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(BadRequest)
    @app.errorhandler(RequestEntityTooLarge)
    def invalid_json(exc):
        return jsonify(error='Invalid JSON or request size'), 400

    @app.before_request
    def canonical_local_host():
        if auth is None or request.method not in ('GET', 'HEAD'):
            return None
        canonical = urlparse(auth.settings.base_url)
        if (canonical.hostname == '127.0.0.1' and
                request.host == f'localhost:{canonical.port or 80}'):
            path = request.path
            if request.query_string:
                path += '?' + request.query_string.decode('latin1')
            return redirect(auth.settings.base_url + path, code=307)
        return None

    @app.before_request
    def require_account():
        if auth is None or (request.method == 'GET' and request.path in ('/api/health', '/api/auth/me')):
            return None
        if not request.path.startswith('/api/'):
            return None
        token = request.cookies.get(SESSION_COOKIE)
        user = auth.resolve_session(token)
        if not user:
            return jsonify(error='Sign in to access your paper account'), 401
        g.user, g.session_token = user, token
        return None

    @app.before_request
    def protect_writes():
        if request.method != 'POST' or not request.path.startswith('/api/'):
            return None
        origin = request.headers.get('Origin')
        allowed = ({auth.settings.base_url} if auth is not None else
                   {f'http://127.0.0.1:{port}', f'http://localhost:{port}'})
        if auth is None or urlparse(auth.settings.base_url).hostname in ('127.0.0.1', 'localhost'):
            allowed.update({'http://127.0.0.1:5173', 'http://localhost:5173'})
        if origin and origin not in allowed:
            return jsonify(error='Cross-origin writes are not allowed'), 403
        if auth is not None and not auth.valid_csrf(g.session_token, request.headers.get('X-CSRF-Token')):
            return jsonify(error='Invalid or missing CSRF token'), 403
        if request.path == '/api/auth/logout':
            return None
        if request.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return jsonify(error='Content-Type must be application/json'), 400
        if not request.content_length or request.content_length > 16384:
            return jsonify(error='Invalid request size'), 400
        return None

    def body():
        return request.get_json()

    if auth is not None:
        @app.get('/auth/login')
        def login():
            if auth.resolve_session(request.cookies.get(SESSION_COOKIE)):
                return redirect(auth.settings.base_url + '/#terminal')
            session.clear()
            session.permanent = True
            response = remote.authorize_redirect(
                auth.settings.base_url + '/auth/callback', nonce=secrets.token_urlsafe(24))
            response.delete_cookie(SESSION_COOKIE)
            return response

        @app.get('/auth/callback')
        def callback():
            from authlib.integrations.base_client.errors import OAuthError
            try:
                token = remote.authorize_access_token()
                profile = token['userinfo']
                if str(profile.get('iss', '')).rstrip('/') != auth.settings.issuer or not profile.get('sub'):
                    raise ValueError('Identity provider returned an invalid identity')
                user = auth.get_or_create_user(auth.settings.issuer, profile['sub'],
                                               profile.get('name') or profile.get('email') or '')
                if user['disabled']:
                    raise PermissionError('This account is disabled')
                session_token = auth.create_session(user)
            except (OAuthError, KeyError, ValueError, PermissionError):
                session.clear()
                return redirect(auth.settings.base_url + '/?auth_error=signin', code=303)
            session.clear()
            response = redirect(auth.settings.base_url + '/#terminal')
            response.set_cookie(SESSION_COOKIE, session_token, max_age=SESSION_SECONDS,
                                httponly=True, secure=auth.settings.secure_cookies,
                                samesite='Lax', path='/')
            return response

        @app.get('/api/auth/me')
        def auth_me():
            token = request.cookies.get(SESSION_COOKIE)
            user = auth.resolve_session(token)
            if not user:
                return jsonify(authenticated=False), 401
            return jsonify(authenticated=True, user={key: user[key] for key in
                                                   ('id', 'display_name', 'subject')},
                           csrf_token=auth.csrf_token(token))

        @app.post('/api/auth/logout')
        def logout():
            auth.revoke_session(g.session_token)
            session.clear()
            response = jsonify(ok=True)
            response.delete_cookie(SESSION_COOKIE)
            return response

    @app.get('/api/options')
    def options():
        return jsonify(current_exchange().option_chain(request.args.get('symbol', ''), request.args.get('expiry')))

    @app.get('/api/catalogue')
    def catalogue():
        return jsonify(current_exchange().catalogue(request.args.get('q', ''), request.args.get('exchange', 'ALL'),
                                         int(request.args.get('offset', '0')), int(request.args.get('limit', '40'))))

    @app.get('/api/state')
    def state():
        history_after = request.args.get('history_after')
        if history_after is not None:
            try:
                parsed = datetime.fromisoformat(history_after.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    raise ValueError
                history_after = parsed.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError):
                raise ValueError('history_after must be a timezone-aware ISO timestamp')
        return jsonify(current_exchange().state(history_after=history_after))

    @app.get('/api/investing/overview')
    def investing_overview():
        return jsonify(investment_overview(current_exchange().investing_state()))

    @app.get('/api/health')
    def health():
        return jsonify(ok=True, mode='SIMULATED')

    @app.route('/api/journal', methods=['GET', 'POST'])
    def journal():
        return jsonify(current_exchange().journal(body() if request.method == 'POST' else None))

    @app.route('/api/learning', methods=['GET', 'POST'])
    def learning():
        return jsonify(current_exchange().learning(body() if request.method == 'POST' else None))

    @app.get('/api/report')
    def report():
        return jsonify(current_exchange().report())

    @app.post('/api/catalogue/activate')
    def activate_catalogue():
        return jsonify(current_exchange().activate(body()))

    @app.post('/api/options/activate')
    def activate_option():
        return jsonify(current_exchange().activate_option(body()))

    @app.post('/api/trade-plan')
    def trade_plan():
        return jsonify(current_exchange().trade_plan(body()))

    @app.post('/api/order-preview')
    def order_preview():
        return jsonify(current_exchange().order_preview(body()))

    @app.post('/api/orders')
    def orders():
        return jsonify(order=current_exchange().submit(body()))

    @app.post('/api/orders/<int:order_id>/cancel')
    def cancel_order(order_id):
        return jsonify(order=current_exchange().cancel(order_id))

    @app.post('/api/reset')
    def reset():
        return jsonify(current_exchange().reset())

    @app.errorhandler(404)
    def not_found(_exc):
        if request.path.startswith('/api/'):
            return jsonify(error='Not found'), 404
        return send_from_directory(frontend_root, 'index.html')

    @app.get('/')
    @app.get('/<path:filename>')
    def frontend(filename=''):
        if filename.startswith('api/'):
            return jsonify(error='Not found'), 404
        target = frontend_root / filename
        if filename and target.is_file():
            return send_from_directory(frontend_root, filename)
        return send_from_directory(frontend_root, 'index.html')

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--database', default=configured_database_url())
    args = parser.parse_args()
    if not args.database:
        parser.error('Configure PostgreSQL in DATABASE_URL or .env.local; use --database explicitly for an SQLite test')
    settings = AuthSettings.from_environment()
    auth = AuthStore(args.database, settings)
    exchange = ExchangeManager(args.database)
    stop = threading.Event()
    def feed():
        while not stop.wait(2):
            exchange.tick()
    threading.Thread(target=feed, daemon=True).start()
    app = create_app(exchange, args.port, auth=auth)
    print(f'Paper trader: http://127.0.0.1:{args.port} — SYNTHETIC DEMO DATA ONLY', flush=True)
    try:
        app.run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == '__main__':
    main()
