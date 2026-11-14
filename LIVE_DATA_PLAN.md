# Live prices with paper execution

Status as checked on 26 October 2026: **not connected**. Orders remain virtual. The current application uses synthetic prices and illustrative instruments; it must not be described as live-market trading.

## Dependency to resolve first

The [NSE member circular of 20 April 2023](https://archives.nseindia.com/content/circulars/COMP56426.pdf) directs members to restrict NSE data use to legitimate client trading, excluding gaming and virtual trading. [Kite's standard API terms](https://kite.trade/terms/) explicitly prohibit use of APIs/live data for virtual/mock trading apps. [NSE website terms](https://www.nseindia.com/static/nse-terms-of-use) also exclude simulation use and automated scraping.

[Groww's official quote API documentation](https://groww.in/trade-api/docs/curl/live-data) describes stock and F&O quotes and bid/offer depth. That establishes a technical capability, not permission for paper trading. No applicable permission was verified. The [SEBI May 2026 circular](https://www.sebi.gov.in/sebi_data/attachdocs/may-2026/1778242522289.pdf) sets a 30-day lag for sharing data for educational activities, effective July 2026, with a specific NISM exception. A provider agreement must be consistent with applicable exchange and regulatory requirements.

Do not buy a subscription on the assumption that it permits this use. Do not substitute scraped NSE/broker website prices.

## Draft question for Groww or an authorised data provider

This is a draft only; no message has been sent.

> I want to build a private application for my own learning that displays NSE equity and index-option quotes and simulates orders with virtual money. It will not place broker orders, accept deposits, award prizes, or distribute data to other users. Do your terms and applicable exchange permissions expressly allow supplying live data for this exact paper-trading use case? If so, please identify the applicable agreement/approval and allowed display, storage, replay and market-depth usage. Please also distinguish any conditions for a future public version. If live use is unavailable, what historical data and replay uses are permitted?

## Implementation after an eligible source is established

1. Add the provider adapter on the server, with credentials stored locally outside source files and never returned to the browser. Use market-data endpoints only.
2. Load the provider's exchange instrument catalogue: exchange-qualified identity, actual expiry, strike, option type, lot size and tick size. Do not map synthetic demo symbols directly to live contracts.
3. Keep a separate account/database for live-price paper trading. Preserve the existing demo history without mixing prices or revaluing demo positions against actual contracts.
4. Normalise quotes with instrument identity, exchange/provider timestamp, receipt timestamp, bid/ask and quantities, LTP, source and explicit live/delayed status. Reconnection alone must not make old quotes fresh.
5. Enforce session/calendar rules and per-instrument freshness. Pause fills during disconnection, unavailable depth or stale quotes. Never silently fall back to synthetic quotes in live mode.
6. Use depth-limited simulated fills, explicit latency/slippage assumptions and verified margin/charge rules. A live quote does not make simulated exchange queue position or execution exact.
7. Validate replay fixtures, expired symbols, session closure, reconnects, duplicate events and accounting reconciliation before enabling the mode.

Groww's documented snapshot endpoint is `GET /v1/live-data/quote` with `exchange`, `segment` and `trading_symbol`; the CASH and FNO segments cover the relevant instruments. This is a candidate technical mapping, **not an implemented or approved connector**. A streaming adapter may be preferable after evaluating permitted depth and timestamp semantics.

If no permitted live source is available, keep synthetic mode or implement explicitly licensed historical replay with the applicable data lag. Real-money order placement is outside this application's scope.

## Additional routes investigated

- [NSE Data real-time subscriptions](https://www.nseindia.com/static/market-data/real-time-data-subscription) describe direct feeds and authorised vendors. A subscription is not blanket permission for simulated trading; intended use must be agreed and compatible with the restrictions above.
- [Global Datafeeds](https://globaldatafeeds.in/) advertises market-data APIs, including Indian exchange coverage. This is a candidate for a specific use-case enquiry, not a verified permitted source for this app.
- [TrueData](https://www.truedata.in/information/pricing) advertises real-time and historical APIs. Its technical offering does not establish permission for this simulator; request a use-specific written answer before purchase.
- [NSE's advanced F&O course page](https://www.nseindia.com/static/learn/online-courses-advance-future-and-options) describes simulator-based practical training through NSE Smart. That is a possible separate learning route to investigate with the course provider, not an API entitlement we can embed here.

No provider has been contacted, no subscription purchased, and no permission granted. Other websites claiming live paper trading do not establish an applicable right for this app. A 15-minute-delayed feed is not automatically a permitted educational feed either.

## Instrument coverage versus price coverage

The documented [Groww instrument download](https://groww.in/trade-api/docs/curl/instruments) supplies reference identifiers and contract metadata, not live prices. The local catalogue uses a dated snapshot for search and explicitly marks synthetic pricing. An equity instrument type in a broker's CASH segment may also include funds or debt. Counts must be described as exchange entries, not unique stocks or unique companies. Listing status, trading restrictions and contract metadata require refresh/verification before live use.
