"""Normalize an explicitly supplied Groww instrument CSV; never downloads or adds prices."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCE = 'https://growwapi-assets.groww.in/instruments/instrument.csv'
DOCS = 'https://groww.in/trade-api/docs/curl/instruments'
GROUPS = {'NSE': {'EQ', 'SM'}, 'BSE': {'A', 'B', 'X', 'M'}}
TRADE_TO_TRADE = {'NSE': {'BE', 'BZ', 'ST', 'SZ'},
                  'BSE': {'T', 'XT', 'MT', 'Z', 'ZP'}}


def number(value, integer=False):
    try:
        value = float(value)
        if value <= 0 or (integer and not value.is_integer()):
            return None
        return int(value) if integer else value
    except (ValueError, TypeError):
        return None


def normalize(row):
    item = {key: row[key] for key in ('exchange', 'exchange_token', 'trading_symbol', 'name', 'series', 'isin', 'instrument_type')}
    item['id'] = f"{row['exchange']}:{row['exchange_token']}"
    item['lot_size'] = number(row['lot_size'], integer=True)
    item['tick_size'] = number(row['tick_size'])
    for flag in ('buy_allowed', 'sell_allowed'):
        item[flag] = {'1': True, '0': False}.get(row[flag])
    restriction = ''
    if row['instrument_type'] != 'EQ':
        restriction = 'Search only: index or non-equity instrument; no simulation model.'
    elif row['series'] in TRADE_TO_TRADE[row['exchange']]:
        restriction = 'Search only: trade-to-trade settlement is not implemented.'
    elif row['series'] not in GROUPS[row['exchange']]:
        restriction = 'Search only: debt, fund, or unrecognised series/group; no simulation model.'
    elif not item['lot_size'] or not item['tick_size']:
        restriction = 'Search only: valid lot size and tick size are unavailable.'
    elif item['buy_allowed'] is None or item['sell_allowed'] is None:
        restriction = 'Search only: provider dealing permissions are unknown.'
    elif not item['buy_allowed'] and not item['sell_allowed']:
        restriction = 'Search only: provider snapshot disables buying and selling.'
    item.update(can_simulate=not bool(restriction), restriction=restriction)
    return item


def build(source, retrieved_at):
    with source.open(newline='', encoding='utf-8-sig') as stream:
        items = [normalize(row) for row in csv.DictReader(stream)
                 if row['exchange'] in ('NSE', 'BSE') and row['segment'] == 'CASH']
    counts = Counter(item['exchange'] for item in items)
    if len({i['id'] for i in items}) != len(items):
        raise ValueError('Duplicate exchange/token identifiers in source')
    items.sort(key=lambda i: (i['trading_symbol'], i['exchange'], i['id']))
    coverage = dict(total=len(items), nse=counts['NSE'], bse=counts['BSE'], retrieved_at=retrieved_at,
                    source=SOURCE, docs=DOCS, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    notes='Broker instrument snapshot, not a guaranteed exhaustive active-exchange list. All NSE/BSE CASH rows retained, including bonds, funds and indices; these are not all stocks. Metadata only, with no prices or valuations. Simulation support uses a conservative series/group allowlist; actual settlement and dealing rules are not reproduced. No F&O rows imported.')
    return dict(coverage=coverage, items=items)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--retrieved-at', required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'data'/'catalogue.json')
    args = parser.parse_args()
    result = build(args.csv, args.retrieved_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')
    print(json.dumps(result['coverage'], indent=2))
