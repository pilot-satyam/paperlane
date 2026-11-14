import unittest

from investing import investment_overview


class InvestmentOverviewTests(unittest.TestCase):
    def test_only_long_equities_enter_investment_totals(self):
        state = {
            'updated_at': '2026-11-14T10:00:00+00:00',
            'instruments': [
                {'symbol': 'AAA', 'name': 'Alpha', 'kind': 'EQUITY', 'ltp': 120, 'change_pct': 2},
                {'symbol': 'BBB', 'name': 'Beta', 'kind': 'EQUITY', 'ltp': 40, 'change_pct': -1},
                {'symbol': 'OPT', 'name': 'Alpha call', 'kind': 'OPTION', 'ltp': 20, 'change_pct': 5},
            ],
            'positions': [
                {'symbol': 'AAA', 'quantity': 10, 'average_price': 100},
                {'symbol': 'BBB', 'quantity': -5, 'average_price': 50},
                {'symbol': 'OPT', 'quantity': 10, 'average_price': 10},
            ],
            'history': {'AAA': [{'time': 't1', 'value': 100}, {'time': 't2', 'value': 120}]},
        }
        overview = investment_overview(state)
        self.assertEqual(overview['summary'], {
            'holding_count': 1, 'cost_basis': 1000, 'market_value': 1200,
            'unrealized_pnl': 200, 'return_pct': 20.0,
        })
        self.assertEqual(overview['holdings'][0]['allocation_pct'], 100.0)
        self.assertEqual([item['symbol'] for item in overview['candidates']], ['AAA', 'BBB'])
        self.assertEqual(overview['candidates'][0]['observed_points'], 2)
        self.assertEqual(overview['candidates'][1]['observed_from'], None)

    def test_empty_holdings_have_no_misleading_return(self):
        state = {'updated_at': 't', 'instruments': [], 'positions': [], 'history': {}}
        overview = investment_overview(state)
        self.assertEqual(overview['summary']['market_value'], 0)
        self.assertIsNone(overview['summary']['return_pct'])
        self.assertEqual(overview['holdings'], [])


if __name__ == '__main__':
    unittest.main()
