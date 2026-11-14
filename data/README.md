# Instrument catalogue provenance

`catalogue.json` contains **12,824 NSE/BSE CASH records**: 4,334 NSE and 8,490 BSE records. This is a broker instrument snapshot, not a guaranteed exhaustive list of currently active exchange listings. CASH includes bonds, funds, ETFs and indices as well as equities; an `EQ` provider type alone does not establish that an instrument is a company stock.

- Retrieved: **2026-10-26**.
- Source: https://growwapi-assets.groww.in/instruments/instrument.csv
- Provider documentation: https://groww.in/trade-api/docs/curl/instruments
- Original CSV SHA-256: `f34513908b688b2fbb3a878d2660ef6cd7bca271320c9cbd5f076e7577baa2e4`
- Normalization: all rows with exchange NSE/BSE and segment CASH, without deduplication by name or ISIN; exchange/token IDs are unique. No F&O rows or prices imported.

The import preserves exchange, token, trading symbol, name, series, ISIN, instrument type, lot size, tick size and provider buy/sell flags. Unsupported or unknown groups remain searchable with an explicit restriction. Simulation supports only the NSE EQ/SM and BSE A/B/X/M groups when valid dealing metadata exists. NSE BE/BZ/ST/SZ and BSE T/XT/MT/Z/ZP are search-only because trade-to-trade settlement is not implemented. Other groups are also search-only. This conservative allowlist is an application policy, not an assertion that exchange settlement, auction, surveillance or intraday rules have been implemented. A provider sell-only flag does not establish real-market shorting eligibility.

Settlement references: [NSE periodic review and trade-to-trade rules](https://www.nseindia.com/static/regulations/movement-securities-periodic-review), [NSE series legend](https://www.nseindia.com/static/market-data/legend-of-series), and [BSE master circular](https://www.bseindia.com/markets/MarketInfo/DownloadAttach.aspx?attachedId=9ce6001b-bcb5-4d63-a08f-26ab83e2051a&id=20250430-59). Group membership and exchange rules can change; this is a dated metadata snapshot.

Run `python3 scripts/import_catalogue.py /path/to/instrument.csv --retrieved-at YYYY-MM-DD` from the application directory to rebuild deliberately from a new downloaded snapshot. Dates and hashes describe the supplied source, never an automatic freshness guarantee.

Catalogue activation does not retrieve a market price. New instruments receive a deterministic arbitrary synthetic seed in approximately ₹25–₹5,000, rounded to the imported tick. This is not a valuation or current price. Imported lot/tick metadata and dealing flags apply to simulated orders after activation. Original demo instruments retain their existing account/history keys; their prices remain synthetic. At most 100 total instruments are active at once; all 12,824 records remain searchable without being subscribed to or continuously ticked.
