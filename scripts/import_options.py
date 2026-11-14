"""Import NSE option metadata only; no market prices."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

COLUMNS = ['id', 'trading_symbol', 'underlying_symbol', 'underlying_token', 'option_type', 'strike', 'expiry', 'lot_size', 'tick_size', 'buy_allowed', 'sell_allowed', 'is_reserved']

def build(path, retrieved_at):
    rows = []
    with path.open(newline='', encoding='utf-8-sig') as stream:
        for r in csv.DictReader(stream):
            if r['exchange'] != 'NSE' or r['segment'] != 'FNO' or r['instrument_type'] not in ('CE','PE'):
                continue
            rows.append([f"NSE:FNO:{r['exchange_token']}",r['trading_symbol'],r['underlying_symbol'],r['underlying_exchange_token'],r['instrument_type'],float(r['strike_price']),r['expiry_date'],int(r['lot_size']),float(r['tick_size']),r['buy_allowed']=='1',r['sell_allowed']=='1',r['is_reserved']=='1'])
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError('Duplicate option IDs')
    return dict(columns=COLUMNS, rows=rows, coverage=dict(total=len(rows),retrieved_at=retrieved_at,source='https://growwapi-assets.groww.in/instruments/instrument.csv',source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),notes='NSE CE/PE metadata snapshot only; no prices, live availability, Greeks or exchange execution data. BSE cash maps to NSE options where an unambiguous ISIN match exists. Reserved contracts are searchable but unavailable for new simulated orders.'))

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path)
    parser.add_argument('--retrieved-at',required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'data'/'options.json')
    args=parser.parse_args()
    data=build(args.csv,args.retrieved_at)
    args.output.write_text(json.dumps(data,separators=(',',':'))+'\n')
    print(json.dumps(data['coverage'],indent=2))
