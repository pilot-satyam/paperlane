import tempfile
import sqlite3
import threading
import time
import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path
from server import Exchange, INITIAL, create_app, synthetic_option_value, calibrate_synthetic_volatility, technical_snapshot


TECH_START = datetime(2026,10,26,tzinfo=timezone.utc)

def technical_time(seconds):
    return (TECH_START+timedelta(seconds=seconds)).isoformat()


def technical_points(values):
    return [dict(time=technical_time(index*10+8),value=value) for index,value in enumerate(values)]


class TechnicalIndicatorTests(unittest.TestCase):
    def test_rsi_flat_all_gain_and_all_loss(self):
        for values, expected in [([100]*20,50),(list(range(1,21)),100),(list(range(20,0,-1)),0)]:
            snapshot=technical_snapshot(technical_points(values),technical_time(200))
            self.assertEqual(snapshot['rsi14'],expected)
            self.assertEqual(snapshot['status'],'available')

    def test_wilder_smoothing_and_ema_seed(self):
        values=[100]
        for index in range(14):
            values.append(values[-1]+(1 if index%2==0 else -1))
        values.append(values[-1]+2)
        snapshot=technical_snapshot(technical_points(values),technical_time(160))
        self.assertAlmostEqual(snapshot['rsi14'],100*8.5/15)
        rising=technical_snapshot(technical_points(list(range(1,22))),technical_time(210))
        self.assertEqual(rising['sma10'],16.5)
        self.assertEqual(rising['ema20'],11.5)

    def test_only_completed_bars_no_future_or_partial_lookahead(self):
        points=technical_points(list(range(1,21)))
        points.extend([dict(time=technical_time(201),value=10000),dict(time=technical_time(205),value=20000),dict(time=technical_time(308),value=99999)])
        snapshot=technical_snapshot(list(reversed(points)),technical_time(205))
        self.assertEqual(snapshot['bar_count'],20)
        self.assertEqual(snapshot['last_close'],20)
        self.assertEqual(snapshot['last_bar_at'],technical_time(200))
        self.assertEqual(snapshot['freshness'],'fresh')
        self.assertEqual(snapshot['ema20'],10.5)

    def test_minimum_history_and_missing_intervals(self):
        fourteen=technical_snapshot(technical_points(list(range(1,15))),technical_time(140))
        self.assertIsNone(fourteen['rsi14'])
        self.assertIsNotNone(fourteen['sma10'])
        self.assertIsNone(fourteen['ema20'])
        fifteen=technical_snapshot(technical_points(list(range(1,16))),technical_time(150))
        self.assertEqual(fifteen['rsi14'],100)
        self.assertEqual(fifteen['status'],'insufficient_history')
        points=technical_points(list(range(1,31)))
        del points[10]
        gap=technical_snapshot(points,technical_time(400))
        self.assertEqual(gap['gap_count'],1)
        self.assertEqual(gap['contiguous_bar_count'],19)
        self.assertEqual(gap['freshness'],'stale')
        self.assertIsNone(gap['ema20'],'EMA must not bridge a missing interval')
        empty=technical_snapshot([],technical_time(0))
        self.assertEqual(empty['freshness'],'no_data')
        self.assertIsNone(empty['last_close'])


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.e = Exchange(':memory:')

    def tearDown(self):
        self.e.db.close()

    def test_option_price_dynamics_and_legacy_anchor(self):
        spot, years = 5630, 2/365
        quotes = [(5000,644.55),(5300,344.55)]
        vols = [calibrate_synthetic_volatility(spot,k,years,p,'CE') for k,p in quotes]
        initial = [synthetic_option_value(spot,k,years,v,'CE') for (k,p),v in zip(quotes,vols)]
        for actual, (_,target) in zip(initial,quotes):
            self.assertAlmostEqual(actual,target,places=6)
        moved = [synthetic_option_value(spot+20,k,years,v,'CE') for (k,p),v in zip(quotes,vols)]
        net_change = 125*((moved[1]-initial[1])-(moved[0]-initial[0]))
        self.assertGreater(abs(net_change),1)
        self.assertAlmostEqual(synthetic_option_value(100,100,1,.3,'CE'),synthetic_option_value(100,100,1,.3,'PE'))
        self.assertEqual(synthetic_option_value(110,100,0,.3,'CE'),10)

    def submit(self, side='BUY', quantity=10, symbol='RELIANCE', **kwargs):
        return self.e.submit(dict(symbol=symbol, side=side, type='MARKET', quantity=quantity, **kwargs))

    def test_round_trip_and_cash_conservation(self):
        buy = self.submit()
        sell = self.submit('SELL')
        expected = (sell['filled_price']-buy['filled_price'])*10-buy['fee']-sell['fee']
        a = self.e.account()
        self.assertAlmostEqual(a['cash'], INITIAL+expected)
        self.assertAlmostEqual(a['realized_pnl'], expected)
        self.assertEqual(self.e.positions(), {})
        self.assertAlmostEqual(a['equity']-INITIAL, a['realized_pnl']+a['unrealized_pnl'])

    def test_reversal_and_average(self):
        self.submit(quantity=10)
        sell = self.submit('SELL', quantity=20)
        self.assertEqual(self.e.positions()['RELIANCE']['quantity'], -10)
        self.assertEqual(self.e.positions()['RELIANCE']['average_price'], sell['filled_price'])
        self.submit(quantity=10)
        self.assertEqual(self.e.positions(), {})
        a = self.e.account()
        self.assertAlmostEqual(a['cash']-INITIAL, a['realized_pnl'])

    def test_limit_reservation_and_cancel(self):
        before = self.e.account()['available_margin']
        o = self.e.submit(dict(symbol='RELIANCE', side='BUY', type='LIMIT', quantity=100, limit_price=1000))
        self.assertEqual(o['status'], 'PENDING')
        self.assertAlmostEqual(before-self.e.account()['available_margin'], 100050)
        self.assertEqual(self.e.cancel(o['id'])['status'], 'CANCELLED')
        self.assertEqual(before, self.e.account()['available_margin'])

    def test_limit_matches_ask_not_last_price(self):
        i = self.e.instruments['RELIANCE']
        o = self.e.submit(dict(symbol='RELIANCE', side='BUY', type='LIMIT', quantity=1, limit_price=i['ltp']))
        self.assertEqual(o['status'], 'PENDING')
        with patch('server.random.gauss', return_value=0):
            self.e.tick()
        self.assertEqual(self.e.order_dict(o['id'])['status'], 'PENDING')
        with patch('server.random.gauss', return_value=-.01):
            self.e.tick()
        self.assertEqual(self.e.order_dict(o['id'])['status'], 'FILLED')
        self.assertLessEqual(self.e.order_dict(o['id'])['filled_price'], o['limit_price'])

    def test_sell_limit_uses_bid_and_tick_matching(self):
        self.submit(quantity=1)
        i = self.e.instruments['RELIANCE']
        o = self.e.submit(dict(symbol='RELIANCE', side='SELL', type='LIMIT', quantity=1, limit_price=i['ltp']))
        with patch('server.random.gauss', return_value=0):
            self.e.tick()
        self.assertEqual(self.e.order_dict(o['id'])['status'], 'PENDING')
        with patch('server.random.gauss', return_value=.01):
            self.e.tick()
        self.assertEqual(self.e.order_dict(o['id'])['status'], 'FILLED')
        self.assertGreaterEqual(self.e.order_dict(o['id'])['filled_price'], o['limit_price'])

    def test_distant_sell_limit_still_reserves_short_margin(self):
        o = self.e.submit(dict(symbol='NIFTY-24000-CE', side='SELL', type='LIMIT', quantity=50, limit_price=50000))
        self.assertEqual(o['status'], 'PENDING')
        self.assertGreaterEqual(self.e.account()['used_margin'], 360000)

    def test_short_option_margin(self):
        o = self.submit('SELL', 50, 'NIFTY-24000-CE')
        self.assertEqual(o['status'], 'FILLED')
        self.assertEqual(self.e.account()['used_margin'], 360000)
        self.assertEqual(self.submit('SELL', 150, 'NIFTY-24100-CE')['status'], 'REJECTED')
        self.assertEqual(self.submit('BUY', 50, 'NIFTY-24000-CE')['status'], 'FILLED')
        self.assertEqual(self.e.account()['used_margin'], 0)

    def test_invalid_and_stale(self):
        for q in (0, -1, True, 1.5, '5'):
            with self.assertRaises(ValueError):
                self.submit(quantity=q)
        with self.assertRaises(ValueError):
            self.submit(symbol='NIFTY')
        with self.assertRaises(ValueError):
            self.submit(quantity=1, symbol='NIFTY-24000-CE')
        self.e.last_tick = time.monotonic()-20
        with self.assertRaises(ValueError):
            self.submit()

    def test_under_margin_account_can_close(self):
        self.submit('SELL', 100, 'NIFTY-24000-CE')
        self.e.instruments['NIFTY']['ltp'] = 50000
        self.assertLess(self.e.account()['available_margin'], 0)
        self.assertEqual(self.submit('BUY', 50, 'NIFTY-24000-CE')['status'], 'FILLED')

    def test_state_history_is_snapshot(self):
        state = self.e.state()
        count = len(state['history']['NIFTY'])
        self.e.tick()
        self.assertEqual(len(state['history']['NIFTY']), count)

    def test_state_history_delta_and_retention_fallback(self):
        initial = self.e.state()
        self.assertEqual(initial['history_mode'], 'snapshot')
        self.e.tick()
        delta = self.e.state(initial['history_cursor'])
        self.assertEqual(delta['history_mode'], 'delta')
        self.assertEqual(len(delta['history']['NIFTY']), 1)
        self.assertGreater(delta['history_cursor'], initial['history_cursor'])
        self.assertEqual(self.e.state(delta['history_cursor'])['history'], {})
        self.e.history['NIFTY'] = technical_points(list(range(1, 1801)))
        refreshed = self.e.state('2025-01-01T00:00:00+00:00')
        self.assertEqual(refreshed['history_mode'], 'snapshot')
        self.assertEqual(len(refreshed['history']['NIFTY']), 1800)

    def test_concurrent_buy_never_overspends(self):
        threads = [threading.Thread(target=self.submit, kwargs={'quantity':100}) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertGreaterEqual(self.e.account()['available_margin'], 0)
        self.assertEqual(len(list(self.e.db.execute("SELECT * FROM orders WHERE status='FILLED'"))), 6)

    def test_restart_persistence_and_pending_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'ledger.db'
            e = Exchange(p)
            e.submit(dict(symbol='RELIANCE', side='BUY', type='MARKET', quantity=1))
            e.submit(dict(symbol='TCS', side='BUY', type='LIMIT', quantity=1, limit_price=1))
            e.journal(dict(text='My trade rationale'))
            e.tick()
            price = e.instruments['RELIANCE']['ltp']
            cash = e.account()['cash']
            e.db.close()
            e = Exchange(p)
            self.assertEqual(e.account()['cash'], cash)
            self.assertEqual(e.instruments['RELIANCE']['ltp'], price)
            self.assertEqual(e.positions()['RELIANCE']['quantity'], 1)
            self.assertEqual(e.order_dict(2)['status'], 'CANCELLED')
            self.assertEqual(e.journal()['notes'][0]['text'], 'My trade rationale')
            e.reset()
            self.assertEqual(e.account()['cash'], INITIAL)
            self.assertEqual(e.state()['orders'], [])
            self.assertEqual(e.journal()['notes'], [])
            e.db.close()

    def fixture_fill(self, symbol, side, quantity, price):
        self.e.instruments[symbol].update(ltp=price, bid=price, ask=price)
        return self.submit(side=side, quantity=quantity, symbol=symbol)

    def test_report_technical_uses_initial_entry_and_reversal_snapshot(self):
        self.e.history['RELIANCE']=technical_points(list(range(100,120)))
        with patch('server.now',return_value=technical_time(200)):
            self.submit(quantity=2)
        self.e.history['RELIANCE']=technical_points(list(range(100,121)))
        with patch('server.now',return_value=technical_time(210)):
            self.submit(quantity=1)
        self.e.history['RELIANCE']=technical_points(list(range(100,122)))
        with patch('server.now',return_value=technical_time(220)):
            self.submit('SELL',quantity=4)
        self.e.history['RELIANCE']=technical_points(list(range(100,123)))
        with patch('server.now',return_value=technical_time(230)):
            self.submit(quantity=1)
        before=self.e.db.total_changes
        report=self.e.report()
        self.assertEqual(self.e.db.total_changes,before)
        newest,oldest=report['closed']
        self.assertEqual(oldest['technical']['entry']['as_of'],technical_time(200))
        self.assertEqual(oldest['technical']['entry']['last_close'],119)
        self.assertEqual(oldest['technical']['exit']['as_of'],technical_time(220))
        self.assertEqual(newest['technical']['entry'],oldest['technical']['exit'])
        self.assertEqual(newest['technical']['exit']['as_of'],technical_time(230))
        self.e.history['RELIANCE']=technical_points([9999]*100)
        self.assertEqual(self.e.report(),report,'Later chart changes cannot rewrite recorded indicator context')
        self.e.reset()
        self.assertEqual(self.e.db.execute('SELECT COUNT(*) FROM trade_technical').fetchone()[0],0)

    def test_legacy_fills_missing_technical_are_unavailable(self):
        self.submit(quantity=1)
        self.submit('SELL',quantity=1)
        self.e.db.execute('DELETE FROM trade_technical')
        self.e.history['RELIANCE']=technical_points([100]*100)
        report=self.e.report()
        self.assertEqual(report['closed'][0]['technical']['entry']['status'],'unavailable')
        self.assertEqual(report['closed'][0]['technical']['exit']['status'],'unavailable')
        self.assertIsNone(report['closed'][0]['technical']['entry']['rsi14'])

    def test_technical_snapshots_persist_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'technical.db'
            e=Exchange(path)
            e.history['RELIANCE']=technical_points([100]*20)
            with patch('server.now',return_value=technical_time(200)):
                e.submit(dict(symbol='RELIANCE',side='BUY',type='MARKET',quantity=1))
                e.submit(dict(symbol='RELIANCE',side='SELL',type='MARKET',quantity=1))
            expected=e.report()['closed'][0]['technical']
            e.db.close()
            e=Exchange(path)
            self.assertEqual(e.report()['closed'][0]['technical'],expected)
            e.db.close()

    def test_learning_manual_progress_is_atomic_idempotent_and_whitelisted(self):
        self.assertEqual(self.e.learning(),dict(completed=[],exercises=[],plans=[]))
        result=self.e.learning(dict(lesson_id='basics',exercise_id='limit'))
        self.assertEqual(result['completed'],['basics'])
        self.assertEqual(result['exercises'],['limit'])
        self.e.learning(dict(lesson_id='basics'))
        self.assertEqual(self.e.learning()['completed'],['basics'])
        for invalid in ({}, {'lesson_id':'unknown'}, {'exercise_id':[]}, {'other':'basics'}, {'lesson_id':'orders','exercise_id':'invalid'}):
            with self.assertRaises(ValueError):
                self.e.learning(invalid)
        self.assertEqual(self.e.learning()['completed'],['basics'])
        self.submit()
        self.submit('SELL')
        self.e.journal({'text':'Practice note'})
        self.assertEqual(self.e.learning()['exercises'],['limit'],'Trading/journaling must not auto-complete self-checks')

    def test_expanded_course_progress_preserves_existing_records(self):
        self.e.learning(dict(lesson_id='basics',exercise_id='limit'))
        new_lessons = ['candles','levels','averages','rsi','sizing','expectancy','liquidity','moneyness','greeks','routine']
        for lesson in new_lessons:
            self.e.learning(dict(lesson_id=lesson))
        for exercise in ['candles','indicator','levels','costs']:
            self.e.learning(dict(exercise_id=exercise))
        result = self.e.learning()
        self.assertEqual(set(result['completed']), {'basics', *new_lessons})
        self.assertEqual(set(result['exercises']), {'limit','candles','indicator','levels','costs'})

    def test_order_plan_preview_and_closed_trade_link(self):
        plan=self.e.trade_plan(dict(symbol='RELIANCE',reason='Practise an entry',exit_plan='Exit when my idea changes',max_loss=120,confidence=3))['plans'][0]
        preview=self.e.order_preview(dict(symbol='RELIANCE',side='BUY',quantity=10,plan_id=plan['id']))
        self.assertEqual(preview['plan_max_loss'],120)
        self.assertAlmostEqual(preview['estimated_trade_value'],self.e.instruments['RELIANCE']['ask']*10,places=2)
        self.assertGreater(preview['estimated_full_spread_cost'],0)
        self.assertGreater(preview['estimated_entry_fee'],0)
        for bad in [True,0,99999,'1']:
            with self.assertRaises(ValueError):
                self.submit(plan_id=bad)
        with self.assertRaises(ValueError):
            self.e.order_preview(dict(symbol='TCS',side='BUY',quantity=10,plan_id=plan['id']))
        opening=self.submit(plan_id=plan['id'])
        closing=self.submit('SELL')
        self.assertEqual(opening['plan_id'],plan['id'])
        self.assertIsNone(closing['plan_id'])
        row=self.e.report()['closed'][0]
        self.assertEqual(row['plan']['id'],plan['id'])
        self.assertEqual(row['plan_link_status'],'recorded')
        self.assertEqual(row['entry_trade_id'],self.e.report()['fills'][1]['id'])
        self.assertEqual(row['exit_trade_id'],self.e.report()['fills'][0]['id'])
        self.assertEqual(self.e.state()['trades'][0]['order_id'],closing['id'])
        self.assertEqual(self.e.state()['trades'][1]['plan_id'],plan['id'])

    def test_mixed_opening_plans_are_not_guessed(self):
        plan=self.e.trade_plan(dict(symbol='RELIANCE',reason='First idea',exit_plan='Exit on reversal',max_loss=100,confidence=3))['plans'][0]
        self.submit(quantity=5,plan_id=plan['id'])
        self.submit(quantity=5)
        self.submit('SELL',quantity=10)
        row=self.e.report()['closed'][0]
        self.assertIsNone(row['plan'])
        self.assertEqual(row['plan_link_status'],'ambiguous')

    def test_unplanned_older_fills_remain_unattributed(self):
        self.submit()
        self.submit('SELL')
        row=self.e.report()['closed'][0]
        self.assertIsNone(row['plan'])
        self.assertEqual(row['plan_link_status'],'unavailable')
        self.assertIsNone(self.e.order_preview(dict(symbol='TCS',side='BUY',quantity=1))['plan_max_loss'])

    def test_trade_plan_validation_and_latest_first(self):
        valid=dict(symbol='RELIANCE',reason=' Test setup ',exit_plan=' Exit on thesis failure ',max_loss=500,confidence=3)
        first=self.e.trade_plan(valid)
        self.assertEqual(first['plans'][0]['reason'],'Test setup')
        self.assertTrue(first['plans'][0]['created_at'])
        second=self.e.trade_plan(dict(valid,symbol='TCS'))
        self.assertEqual([p['symbol'] for p in second['plans']],['TCS','RELIANCE'])
        for changes in ({'max_loss':0},{'max_loss':-1},{'max_loss':float('nan')},{'max_loss':float('inf')},{'max_loss':True},{'confidence':0},{'confidence':6},{'confidence':2.5},{'confidence':True},{'reason':' '},{'reason':'x'*2001},{'exit_plan':None},{'symbol':''}):
            with self.assertRaises(ValueError):
                self.e.trade_plan(dict(valid,**changes))
        with self.assertRaises(ValueError):
            self.e.trade_plan({'symbol':'TCS'})
        self.assertEqual(len(self.e.learning()['plans']),2)
        self.assertEqual(self.e.state()['orders'],[],'Plans must not place or enforce orders')

    def test_learning_and_plans_persist_independently_of_account_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'learning.db'
            e=Exchange(path)
            e.learning(dict(lesson_id='risk',exercise_id='journal'))
            e.trade_plan(dict(symbol='TCS',reason='Practise a limit',exit_plan='Review at close',max_loss=100,confidence=2))
            expected=e.learning()
            e.reset()
            self.assertEqual(e.learning(),expected)
            e.db.close()
            e=Exchange(path)
            self.assertEqual(e.learning(),expected)
            e.db.close()

    def test_catalogue_coverage_search_pagination_and_exchange_ids(self):
        report = self.e.catalogue(limit=1)
        self.assertEqual(report['total'], 12824)
        self.assertEqual(report['coverage']['nse'], 4334)
        self.assertEqual(report['coverage']['bse'], 8490)
        first = report['items'][0]['id']
        self.assertNotEqual(first, self.e.catalogue(offset=1, limit=1)['items'][0]['id'])
        nse = self.e.catalogue('INE002A01018', 'NSE')['items']
        bse = self.e.catalogue('INE002A01018', 'BSE')['items']
        self.assertEqual(nse[0]['id'], 'NSE:2885')
        self.assertEqual(bse[0]['id'], 'BSE:500325')
        self.assertEqual(nse[0]['trading_symbol'], bse[0]['trading_symbol'])
        self.assertEqual(self.e.catalogue('no-such-instrument-123')['total'], 0)
        self.assertEqual(self.e.catalogue(offset=999999)['items'], [])
        for kwargs in ({'exchange':'INVALID'}, {'offset':-1}, {'limit':0}, {'limit':101}):
            with self.assertRaises(ValueError):
                self.e.catalogue(**kwargs)

    def test_catalogue_legacy_mapping_and_history_preservation(self):
        self.submit(quantity=2, symbol='RELIANCE')
        before = self.e.state()
        activated = self.e.activate({'id':'NSE:2885'})
        after = self.e.state()
        self.assertEqual(activated['symbol'], 'RELIANCE')
        self.assertEqual(before['positions'], after['positions'])
        self.assertEqual(before['trades'], after['trades'])
        self.assertEqual(before['history'], after['history'])
        self.assertEqual(len(before['instruments']), len(after['instruments']))
        bse = self.e.activate({'id':'BSE:500325'})
        self.assertEqual(bse['symbol'], 'BSE:500325')
        self.assertEqual(bse['instrument']['display_symbol'], 'RELIANCE · BSE')
        self.assertNotEqual(bse['symbol'], activated['symbol'])

    def test_catalogue_activation_tick_lot_and_flags(self):
        item = next(i for i in self.e.catalogue_data['items'] if i['can_simulate'] and i['lot_size'] > 1 and i['tick_size'] >= .05 and i['buy_allowed'])
        activated = self.e.activate({'id':item['id']})
        symbol = activated['symbol']
        with self.assertRaisesRegex(ValueError, 'lot multiple'):
            self.submit(quantity=1, symbol=symbol)
        with self.assertRaisesRegex(ValueError, 'tick size'):
            self.e.submit(dict(symbol=symbol, side='BUY', type='LIMIT', quantity=item['lot_size'], limit_price=1.001))
        self.e.tick()
        for field in ('ltp', 'bid', 'ask'):
            self.assertEqual(Decimal(str(self.e.instruments[symbol][field])) % Decimal(str(item['tick_size'])), 0)
        blocked = next(i for i in self.e.catalogue_data['items'] if i['can_simulate'] and i['buy_allowed'] is False)
        self.e.activate({'id':blocked['id']})
        with self.assertRaisesRegex(ValueError, 'disabled'):
            self.submit(symbol=blocked['id'], quantity=blocked['lot_size'])
        restricted = next(i for i in self.e.catalogue_data['items'] if not i['can_simulate'])
        with self.assertRaisesRegex(ValueError, 'Search only'):
            self.e.activate({'id':restricted['id']})

    def test_catalogue_activation_persists_and_is_deterministic(self):
        identifier = 'BSE:500325'
        initial = self.e.activate({'id':identifier})['instrument']['ltp']
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'paper.db'
            e = Exchange(path)
            instrument = e.activate({'id':identifier})['instrument']
            self.assertEqual(instrument['ltp'], initial)
            self.assertEqual(len(e.instruments), 21)
            e.db.close()
            e = Exchange(path)
            self.assertEqual(e.instruments[identifier]['ltp'], initial)
            self.assertEqual(e.instruments[identifier]['tick_size'], instrument['tick_size'])
            self.assertEqual(len(e.history[identifier]), 1)
            e.db.close()

    def test_catalogue_trade_to_trade_is_search_only(self):
        for exchange, groups in [('NSE', ('BE','BZ','ST','SZ')), ('BSE', ('T','XT','MT','Z','ZP'))]:
            for group in groups:
                item = next(i for i in self.e.catalogue_data['items'] if i['exchange'] == exchange and i['series'] == group)
                self.assertFalse(item['can_simulate'])
                with self.assertRaisesRegex(ValueError, 'trade-to-trade'):
                    self.e.activate({'id':item['id']})

    def test_catalogue_active_cap_does_not_block_search(self):
        candidates = [i for i in self.e.catalogue_data['items'] if i['can_simulate']]
        for item in candidates:
            if len(self.e.instruments) >= 100:
                break
            self.e.activate({'id':item['id']})
        other = next(i for i in candidates if i['id'] not in self.e.instruments and i['trading_symbol'] not in self.e.instruments)
        with self.assertRaisesRegex(ValueError, 'limit reached'):
            self.e.activate({'id':other['id']})
        self.assertEqual(self.e.catalogue()['total'], 12824)

    def test_stop_limit_triggers_then_waits_through_gap(self):
        for side, trigger, limit, movement in [('BUY',1460,1465,.02), ('SELL',1440,1435,-.02)]:
            self.e.reset()
            self.e.instruments['RELIANCE'].update(ltp=1450, bid=1449.27, ask=1450.73)
            order = self.e.submit(dict(symbol='RELIANCE', side=side, type='STOP_LIMIT', quantity=2, trigger_price=trigger, limit_price=limit))
            self.assertEqual(order['status'], 'PENDING')
            self.assertFalse(order['triggered'])
            with patch('server.random.gauss', return_value=0):
                self.e.tick()
            self.assertEqual(self.e.order_dict(order['id'])['status'], 'PENDING')
            self.assertFalse(self.e.order_dict(order['id'])['triggered'])
            with patch('server.random.gauss', return_value=movement):
                self.e.tick()
            triggered = self.e.order_dict(order['id'])
            self.assertEqual(triggered['status'], 'PENDING', 'A gap through the limit must not fill')
            self.assertTrue(triggered['triggered'])
            self.e.instruments['RELIANCE']['ltp'] = trigger
            with patch('server.random.gauss', return_value=0):
                self.e.tick()
            self.assertEqual(self.e.order_dict(order['id'])['status'], 'FILLED')

    def test_stop_limit_reservation_cancel_and_validation(self):
        before = self.e.account()['available_margin']
        order = self.e.submit(dict(symbol='RELIANCE', side='BUY', type='STOP_LIMIT', quantity=2, trigger_price=1460, limit_price=1465))
        self.assertAlmostEqual(before-self.e.account()['available_margin'], 2931.47)
        self.e.cancel(order['id'])
        self.assertEqual(self.e.account()['available_margin'], before)
        self.e.activate({'id':'NSE:2885'})
        for side, trigger, limit in [('BUY',1460,1450),('SELL',1440,1450),('BUY',None,1500),('BUY',float('nan'),1500),('BUY',1460.01,1500)]:
            with self.assertRaises(ValueError):
                self.e.submit(dict(symbol='RELIANCE', side=side, type='STOP_LIMIT', quantity=1, trigger_price=trigger, limit_price=limit))

    def test_stop_columns_migrate_old_database_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'old.db'
            connection = sqlite3.connect(path)
            connection.executescript('''CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, type TEXT, quantity INTEGER, limit_price REAL, status TEXT, filled_price REAL, fee REAL, created_at TEXT, message TEXT, reservation REAL);
            INSERT INTO orders VALUES (1,'RELIANCE','BUY','MARKET',1,NULL,'FILLED',1450,.73,'2026-10-26','old record',0);''')
            connection.close()
            e = Exchange(path)
            old = e.order_dict(1)
            self.assertEqual(old['filled_price'], 1450)
            self.assertEqual(old['status'], 'FILLED')
            self.assertIsNone(old['trigger_price'])
            self.assertFalse(old['triggered'])
            e.db.close()

    @patch('server.option_expired', return_value=False)
    def test_stock_chain_selection_mapping_and_no_fallback(self, _):
        count=len(self.e.instruments)
        chain=self.e.option_chain('RELIANCE')
        self.assertTrue(chain['contracts'])
        self.assertTrue(all(c['underlying_symbol']=='RELIANCE' for c in chain['contracts']))
        self.assertTrue(all(c['lot_size']==500 for c in chain['contracts']))
        self.assertEqual(len(self.e.instruments),count,'Reading chain must not activate contracts')
        bse=self.e.option_chain('BSE:500325')
        self.assertEqual(bse['underlying']['symbol'],'RELIANCE')
        self.assertEqual([c['id'] for c in chain['contracts']],[c['id'] for c in bse['contracts']])
        unknown=self.e.catalogue('20MICRONS','NSE')['items'][0]
        absent=self.e.option_chain(unknown['id'])
        self.assertEqual(absent['contracts'],[])
        self.assertEqual(absent['expiries'],[])
        self.assertNotEqual(absent['underlying']['symbol'],'NIFTY')

    @patch('server.option_expired', return_value=False)
    def test_new_underlying_preview_matches_activated_baseline(self, _):
        item=next(i for i in self.e.catalogue_data['items'] if i['exchange']=='NSE' and i['trading_symbol']=='PERSISTENT' and i['series']=='EQ')
        chain=self.e.option_chain(item['id'])
        self.assertNotIn(chain['underlying']['symbol'],self.e.instruments)
        contract=next(c for c in chain['contracts'] if c['can_trade'])
        self.e.activate_option({'id':contract['id']})
        self.assertEqual(self.e.instruments[chain['underlying']['symbol']]['ltp'],chain['underlying']['ltp'])
        self.assertEqual(self.e.instruments[contract['id']]['ltp'],contract['ltp'])
        reserved=next(c for c in chain['contracts'] if not c['can_trade'])
        with self.assertRaisesRegex(ValueError,'reserved'):
            self.e.activate_option({'id':reserved['id']})

    @patch('server.option_expired', return_value=False)
    def test_stock_option_uses_actual_underlying_margin_and_ticks(self, _):
        chain=self.e.option_chain('RELIANCE')
        contract=min((c for c in chain['contracts'] if c['can_trade']),key=lambda c:abs(c['strike']-1450))
        result=self.e.activate_option({'id':contract['id']})
        instrument=result['instrument']
        self.assertEqual(instrument['underlying'],'RELIANCE')
        self.assertEqual(instrument['contract_id'],contract['id'])
        order=self.submit(side='SELL',symbol=result['symbol'],quantity=contract['lot_size'])
        self.assertEqual(order['status'],'FILLED')
        self.assertEqual(self.e.account()['used_margin'],1450*.3*contract['lot_size'])
        selected=self.e.option_chain(result['symbol'])
        self.assertEqual(selected['underlying']['symbol'],'RELIANCE')
        with patch('server.random.gauss',return_value=0):
            self.e.tick()
        for key in ('ltp','bid','ask'):
            self.assertEqual(Decimal(str(self.e.instruments[result['symbol']][key]))%Decimal(str(contract['tick_size'])),0)

    def test_option_expiry_blocks_activation_orders_and_cancels_pending(self):
        with patch('server.option_expired',return_value=False):
            contract=next(c for c in self.e.option_chain('RELIANCE')['contracts'] if c['can_trade'])
            self.e.activate_option({'id':contract['id']})
            order=self.e.submit(dict(symbol=contract['id'],side='BUY',type='LIMIT',quantity=contract['lot_size'],limit_price=.05))
        with patch('server.option_expired',return_value=True):
            with self.assertRaisesRegex(ValueError,'expired'):
                self.e.activate_option({'id':contract['id']})
            with self.assertRaisesRegex(ValueError,'expired'):
                self.submit(symbol=contract['id'],quantity=contract['lot_size'])
            self.e.tick()
            self.assertEqual(self.e.order_dict(order['id'])['status'],'CANCELLED')
            self.assertEqual(self.e.option_chain('RELIANCE')['contracts'],[])

    @patch('server.option_expired', return_value=False)
    def test_stock_option_persistence_and_existing_trade_nonregression(self, _):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'option.db'
            e=Exchange(path)
            e.submit(dict(symbol='RELIANCE',side='BUY',type='MARKET',quantity=1))
            before=e.state()
            contract=next(c for c in e.option_chain('RELIANCE')['contracts'] if c['can_trade'])
            e.activate_option({'id':contract['id']})
            self.assertEqual(e.state()['trades'],before['trades'])
            self.assertEqual(e.state()['positions'],before['positions'])
            e.db.close()
            e=Exchange(path)
            self.assertEqual(e.instruments[contract['id']]['underlying'],'RELIANCE')
            self.assertEqual(e.state()['trades'],before['trades'])
            e.db.close()

    def test_report_existing_trade_reversal_fixture(self):
        for symbol, side, q, price, fee in [
                ('HDFCBANK', 'BUY', 6, 1752.33, 5.26),
                ('HDFCBANK', 'SELL', 10, 1751.06, 8.76),
                ('HDFCBANK', 'BUY', 4, 1744.48, 3.49),
                ('RELIANCE', 'BUY', 1, 1445.42, .72),
                ('RELIANCE', 'SELL', 1, 1446.38, .72)]:
            order = self.fixture_fill(symbol, side, q, price)
            self.assertEqual(order['fee'], fee)
        changes = self.e.db.total_changes
        report = self.e.report()
        self.assertEqual(self.e.db.total_changes, changes, 'Report must be read-only')
        summary = report['summary']
        self.assertAlmostEqual(summary['gross_pnl'], 19.66)
        self.assertAlmostEqual(summary['total_fees'], 18.95)
        self.assertAlmostEqual(summary['net_realized_pnl'], .71)
        self.assertAlmostEqual(summary['closed_net_pnl'], .71)
        self.assertEqual(summary['open_entry_fees'], 0)
        self.assertEqual(summary['fill_count'], 5)
        self.assertEqual(summary['open_position_count'], 0)
        self.assertAlmostEqual(summary['net_realized_pnl'], self.e.account()['realized_pnl'])
        self.assertEqual(report['fills'][3]['effect'], 'Closed 6 long units and opened 4 short units')
        self.assertEqual([r['direction'] for r in report['closed']], ['LONG', 'SHORT', 'LONG'])
        self.assertAlmostEqual(report['closed'][1]['fees'], 6.994)
        self.assertAlmostEqual(report['closed'][2]['fees'], 10.516)

    def test_report_weighted_average_and_partial_fees(self):
        self.fixture_fill('RELIANCE', 'BUY', 10, 100)
        self.fixture_fill('RELIANCE', 'BUY', 10, 200)
        self.fixture_fill('RELIANCE', 'SELL', 5, 180)
        report = self.e.report()
        summary = report['summary']
        self.assertEqual(report['closed'][0]['entry_price'], 150)
        self.assertEqual(report['closed'][0]['quantity'], 5)
        self.assertEqual(summary['gross_pnl'], 150)
        self.assertAlmostEqual(report['closed'][0]['fees'], .825)
        self.assertAlmostEqual(summary['open_entry_fees'], 1.125)
        self.assertAlmostEqual(summary['net_realized_pnl'], 148.05)
        self.assertAlmostEqual(summary['closed_net_pnl']-summary['open_entry_fees'], summary['net_realized_pnl'])
        self.assertAlmostEqual(summary['net_realized_pnl'], self.e.account()['realized_pnl'])
        self.assertEqual(summary['open_position_count'], 1)

    def test_report_entire_history_and_empty_account(self):
        self.assertEqual(self.e.report()['summary']['net_realized_pnl'], 0)
        self.assertEqual(self.e.report()['fills'], [])
        for _ in range(151):
            self.fixture_fill('RELIANCE', 'SELL', 1, 100)
            self.fixture_fill('RELIANCE', 'BUY', 1, 90)
        report = self.e.report()
        self.assertEqual(len(report['fills']), 302)
        self.assertEqual(len(report['closed']), 151)
        self.assertEqual(report['fills'][0]['id'], 302)
        self.assertAlmostEqual(report['summary']['net_realized_pnl'], self.e.account()['realized_pnl'])
        self.assertEqual(len(self.e.state()['trades']), 300)


class FlaskApiTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(':memory:')
        self.client = create_app(self.exchange, allow_unauthenticated_for_tests=True).test_client()

    def tearDown(self):
        self.exchange.db.close()

    def test_trade_api_round_trip_and_report(self):
        self.assertEqual(self.client.get('/api/health').json, {'ok': True, 'mode': 'SIMULATED'})
        response = self.client.post('/api/orders', json={
            'symbol': 'RELIANCE', 'side': 'BUY', 'type': 'MARKET', 'quantity': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['order']['status'], 'FILLED')
        self.assertEqual(self.client.get('/api/report').json['summary']['fill_count'], 1)
        self.assertEqual(self.client.get('/api/state').json['positions'][0]['quantity'], 1)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_state_api_sends_only_new_history_after_cursor(self):
        first = self.client.get('/api/state').json
        self.exchange.tick()
        response = self.client.get('/api/state', query_string={'history_after': first['history_cursor']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['history_mode'], 'delta')
        self.assertEqual(len(response.json['history']['NIFTY']), 1)
        self.assertEqual(self.client.get('/api/state', query_string={'history_after': 'not-a-time'}).status_code, 400)

    def test_local_write_checks_and_json_errors(self):
        order = {'symbol': 'RELIANCE', 'side': 'BUY', 'type': 'MARKET', 'quantity': 1}
        response = self.client.post('/api/orders', json=order, headers={'Origin': 'https://other.example'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post('/api/orders', data='broken', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/api/orders', data='{}', content_type='text/plain').status_code, 400)
        self.assertEqual(self.client.get('/api/unknown').status_code, 404)
        self.assertEqual(self.client.get('/api/report').json['summary']['fill_count'], 0)


if __name__ == '__main__':
    unittest.main()
