"""Investment view derived from the existing synthetic paper account.

There is no separate investment ledger or live fundamentals feed. These
figures intentionally exclude options, short stock positions and cash.
"""


def investment_overview(market_state):
    equities = {item['symbol']: item for item in market_state['instruments']
                if item['kind'] == 'EQUITY'}
    holdings = []
    for position in market_state['positions']:
        symbol = position['symbol']
        instrument = equities.get(symbol)
        quantity = position['quantity']
        if instrument is None or quantity <= 0:
            continue
        cost = quantity * position['average_price']
        value = quantity * instrument['ltp']
        holdings.append({
            'symbol': symbol,
            'name': instrument['name'],
            'quantity': quantity,
            'average_price': position['average_price'],
            'ltp': instrument['ltp'],
            'cost_basis': round(cost, 2),
            'market_value': round(value, 2),
            'unrealized_pnl': round(value - cost, 2),
            'return_pct': round((value / cost - 1) * 100, 2) if cost > 0 else None,
        })
    market_value = sum(item['market_value'] for item in holdings)
    cost_basis = sum(item['cost_basis'] for item in holdings)
    for item in holdings:
        item['allocation_pct'] = round(item['market_value'] / market_value * 100, 2) if market_value else 0.0
    holdings.sort(key=lambda item: item['market_value'], reverse=True)
    candidates = []
    for symbol, instrument in equities.items():
        points = market_state['history'].get(symbol, [])
        candidates.append({
            'symbol': symbol,
            'name': instrument['name'],
            'ltp': instrument['ltp'],
            'change_pct': instrument['change_pct'],
            'observed_points': len(points),
            'observed_from': points[0]['time'] if points else None,
            'observed_to': points[-1]['time'] if points else None,
        })
    candidates.sort(key=lambda item: item['symbol'])
    return {
        'mode': 'SIMULATED',
        'price_source': 'SYNTHETIC_SAMPLED',
        'shared_account': True,
        'as_of': market_state['updated_at'],
        'summary': {
            'holding_count': len(holdings),
            'cost_basis': round(cost_basis, 2),
            'market_value': round(market_value, 2),
            'unrealized_pnl': round(market_value - cost_basis, 2),
            'return_pct': round((market_value / cost_basis - 1) * 100, 2) if cost_basis > 0 else None,
        },
        'holdings': holdings,
        'candidates': candidates,
    }
