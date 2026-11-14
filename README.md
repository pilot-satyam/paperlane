# Paperlane — trading and investing practice

A local Indian-market-style paper trading and investing app with a React, TypeScript and Vite interface, virtual INR balances, and synthetic stock and option quotes. **This version does not receive real market prices.** The searchable cash catalogue uses a dated broker instrument snapshot. Prices, charges and margin estimates remain illustrative; option contracts use a dated catalogue snapshot.

## Run

Requires Python 3.10 or newer, PostgreSQL, Flask 3, Authlib and the PostgreSQL driver. Set up the database with [DATABASE_SETUP.md](DATABASE_SETUP.md), then configure an Auth0 OIDC application with [AUTH0_SETUP.md](AUTH0_SETUP.md). Copy `.env.example` to ignored `.env.local` and replace every placeholder before starting Flask.

```sh
python3 -m venv .venv
brew services start postgresql@17
.venv/bin/python -m pip install -r backend/requirements-postgres.txt
.venv/bin/python scripts/liquibase.py update
npm --prefix frontend-react ci
npm --prefix frontend-react run build
.venv/bin/python backend/server.py
```

Open http://127.0.0.1:8000 in your browser. Stop with Ctrl+C. The service binds to your computer only; do not expose it publicly.

The Flask API serves `frontend-react/dist` when that build exists and falls back to the earlier `frontend` interface otherwise. To edit the React interface, install Node.js 20 or newer and run:

```sh
cd frontend-react
npm install
npm run dev
```

Vite runs at http://127.0.0.1:5173 and proxies `/api` to Flask on port 8000. Keep Flask running in another terminal. Run `npm run build` to update `frontend-react/dist` before using the React interface on port 8000.

## Database and public launch

The app uses PostgreSQL with a Liquibase-managed schema. The ignored `.env.local` file holds the local connection URL and authentication settings. See [DATABASE_SETUP.md](DATABASE_SETUP.md) for migrations and backup guidance.

The Flask backend has Auth0 OIDC sign-in, PostgreSQL-backed sessions, CSRF protection and a separate account schema for each validated identity. A legacy ledger can be assigned only to an explicitly chosen owner. [PUBLIC_ARCHITECTURE.md](PUBLIC_ARCHITECTURE.md) describes the remaining market-data, ledger, and deployment work before a public launch. Keep the server bound to localhost for now.

The name and avatar in the header open an account menu on hover or click. Each account gets one of eight illustrated avatars selected from its account ID, so the default remains stable across visits. Edit profile can choose or shuffle the character and save a preferred display name and frame color in this browser, scoped to the signed-in account. It does not change the Auth0 sign-in identity; Reset removes the local preference.

The header search works from every signed-in page. It opens charts for instruments already on the practice desk and searches the dated NSE/BSE cash catalogue for more listings. Eligible catalogue results are labelled **Add & open** because adding one creates an arbitrary synthetic practice price; view-only results cannot be added. Search results are suggestions, not a live exchange feed.

## Investing workspace

The **Investing** tab shows long equity holdings from the existing paper account, their virtual market value and allocation, active shares to explore, and the same TradingView Lightweight Charts view, indicators and drawing tools as Terminal. The investing chart has 5m, 1M, 3M, 6M, 1Y, 3Y and 5Y range buttons. The 5m view uses the latest five minutes of observed simulator ticks; longer views generate deterministic demo candles anchored to the instrument's fixed simulator reference price, with weekly candles for 3Y and 5Y. The selected range shows its first and last close, rupee change and percentage change. Its longer-range values do not move with the current simulator quote. A per-share research checklist saves the learner's ticks in this browser and links each step to a relevant investing lesson. The paper share mix panel shows allocation across long share holdings only; it excludes cash, options and shorts and is not a risk score. **Learn → Investing** contains beginner lessons on goals, compounding, company research, valuation, diversification and reviewing decisions. The dashboard's investing overview is served by `GET /api/investing/overview` for the signed-in account.

This is an equity-focused practice view, not a separate investment wallet. It has no company financial statements, valuation data or verified corporate filings. The generated multi-year paths are fictional and never replace the synthetic quote used for paper orders. A licensed history and fundamentals feed is needed for real stock analysis in a public product.

## Learning workflow

1. Select **Start guided practice** for a five-step walk through of a first paper trade. The guide explains the controls and never submits an order.
2. Select a stock or option. Review bid, ask, lot size and the synthetic price chart.
3. In the order ticket, save a plain-English reason, exit rule and planned loss budget. Choose that plan before submitting a paper order. The ticket shows estimated spread and one-fill fees in rupees.
4. Choose buy or sell and market, limit or stop-limit order. Option quantities must be whole contract lots. Review the outcome, virtual cash, margin and positions.
5. Cancel pending orders from the orders view. Review a closed trade in **Trade report**, including any explicitly linked plan and available entry/exit chart markers.

The **Trade report** tab explains each completed portion of a position: weighted-average entry, exit, quantity, gross P&L, allocated fees and net P&L. It includes all stored fills and explains reversals (for example, selling ten shares when holding six closes six and opens four short). The report reconciles booked P&L with charges on any still-open positions. A selected plan is linked to new orders and fills; older trades are never assigned a plan by guesswork. Entry/exit markers appear only where saved synthetic chart history still covers those timestamps. Your existing records are preserved when upgrading.

See [LIVE_DATA_PLAN.md](LIVE_DATA_PLAN.md) for the live-price implementation dependencies. No live connector is enabled.

The starting balance is virtual INR 10,00,000. Option purchases cost premium multiplied by units, plus the demo fee. INR 6,000 is not a fixed minimum. Option selling requires an estimated margin. A purchased option can also be sold to close the existing long position.

## Accuracy boundaries

- Quotes follow a synthetic simulation, not the Indian exchange calendar or real order book.
- Market buys use ask and sells use bid. Limit orders wait until their price condition is satisfied.
- Full simulated fills do not model exchange queue position, partial liquidity or actual market impact.
- Margins and fees are illustrative; they are not exchange SPAN calculations or current broker quotations.
- Expiry settlement, corporate actions, physical delivery, and broker-specific restrictions are not implemented.
- Chart history comes from synthetic quotes. This is not licensed historical market replay.
- Authenticated learners have separate local paper accounts. Production backups, shared quotes and public operations need a later release.

## Next implementation stages

1. Verify a provider's permitted personal simulation use, instrument coverage and costs. Broker API access alone does not establish permission for educational use or redistribution. Kite's published terms explicitly prohibit using its APIs/live market data for virtual/mock trading apps, so it is not an approved route for this prototype. Groww has technical live-feed capabilities, but permission for this use remains unconfirmed.
2. Implement a permitted data adapter and regularly refresh the instrument catalogue. Clearly distinguish feed freshness from application connectivity.
3. Replace demo margin/fee rules with verified, versioned rules; handle contract expiry and settlement.
4. Improve fills with depth, partial execution and latency models; validate outcomes against controlled fixtures.
5. Connect and test the identity provider, then complete the public security, financial-ledger and operational gates before allowing other users access.

See API.md for the frontend/backend contract. Separate local paper accounts are implemented, while a hosted release still needs production operations, ledger hardening, and a review of data rights.

## Data-source findings (26 October 2026)

- [Kite Connect terms](https://kite.trade/terms/): prohibit use of APIs/live market data for virtual/mock trading apps; public display is also restricted.
- [Groww feed documentation](https://groww.in/trade-api/docs/python-sdk/feed): describes streaming capabilities, but is not permission for a paper-trading use case.
- [SEBI circular of 8 May 2026](https://www.sebi.gov.in/sebi_data/attachdocs/may-2026/1778242522289.pdf): sets a 30-day lag for sharing price data for educational activities, effective 1 July 2026, with a specified NISM exception. Applicability and provider agreements need resolution before a real-data release.

## NSE/BSE catalogue

Click **Find stocks** in the trading desk to search by company, symbol or ISIN and filter by exchange. The 26 October 2026 Groww snapshot contains **12,824 CASH entries: 4,334 NSE and 8,490 BSE**. These include funds and other securities, and exchange duplicates; this is not a count of unique companies or a certified complete list of active Indian stocks.

Eligible entries can be added to the practice desk on demand (up to 100 active instruments total). Imported lot sizes, tick sizes and direction flags are enforced. Unsupported series, including trade-to-trade settlement categories, remain searchable but view-only. Newly activated prices start at an arbitrary synthetic value, not a current or historical valuation. NSE option chains now use a separate dated contract snapshot; old demo contracts remain available for existing account history.

## Stock options and interactive charts

Selecting a stock now loads its own NSE option chain, with expiry selection and all/nearest-15 strikes. Matching BSE shares resolve to the NSE underlying by ISIN; the NSE synthetic price may differ from the preserved BSE demo price. Unsupported stocks explicitly show no contracts. Click a CE or PE premium to activate that contract and prepare the BUY ticket; review lot quantity and submit separately. The snapshot contains 87,506 NSE CE/PE records; only unexpired, supported contracts can activate. See [data/OPTIONS.md](data/OPTIONS.md). Expired positions are frozen pending manual future settlement implementation, not automatically settled.

Charts use the TradingView Lightweight Charts package with candles/line, 10-second/1-minute/5-minute intervals, crosshair OHLC in IST, configurable indicators, drawing tools, drag/pinch/scroll navigation, Fit and Latest. Candles aggregate observed synthetic ticks only: newly activated instruments start with little history, gaps are not invented, and no market volume is claimed. Up to 1,800 ticks per active instrument are retained. This is not the complete TradingView platform or a live-data integration.

The app loads the retained chart history once, then polls for new points alongside current quotes and account values every two seconds. If the browser misses the retained history window, the server sends a fresh chart snapshot automatically.

## Option-price dynamics

Snapshot options use a synthetic Black–Scholes illustration with zero rates/dividends and a default 35% annualised volatility, continuous calendar time to the snapshot expiry, and tick rounding. This gives different strikes different sensitivities instead of identical intrinsic-plus-time-value moves. Existing activated premiums are anchored on upgrade by solving a per-contract synthetic volatility from their saved quote; this is not observed market implied volatility. Positions, entry prices and booked results are not rewritten. Net P&L can still legitimately remain unchanged when gains/losses offset or tick rounding hides small moves. No live price accuracy is claimed.

## Learn, practise and review

The sticky **Learn** link opens 22 plain-English lessons with examples and knowledge checks, eight manually self-checked practice exercises, local trade plans, and closed-trade reviews. Six lessons cover F&O basics: futures versus options, calls and puts, reading a chain, expiry payoff, risk, and execution. The **F&O lab** lets learners change a call or put's strike, premium, lot size and expiry price to see an illustrative payoff. Correct quiz responses save lesson completion; exercises never submit or cancel orders automatically. Progress cards show recorded lessons, self-checked exercises and saved plans. Course material links to NSE and SEBI investor education.

Trade report includes **Review this trade** buttons. These are local deterministic explanations of the existing average-cost report, explicitly not AI. They explain direction, quantities, entry/exit, gross P&L, allocated fees and net results. A plan is shown only when explicitly selected for an opening order; mixed entries are marked ambiguous. The review cannot determine whether the learner followed the plan or why they exited. External AI is not connected and no user data is transmitted to an AI service. A future integration requires choosing a provider, server-side credentials and explicit disclosure of the data sent.

Progress and plans are saved in PostgreSQL, survive restart and are intentionally separate from account reset. Plans do not place orders, enforce loss limits or guarantee stop execution. GET/POST `/api/learning` supports whitelisted `lesson_id` and `exercise_id`; POST `/api/trade-plan` accepts `symbol,reason,exit_plan,max_loss,confidence`. The guided walkthrough and chart drawings/settings are saved in this browser.

## Indicators, drawings and clearer reviews

Chart controls include configurable SMA, EMA and Wilder RSI in its own synchronized pane, with editable guide levels (40/60 by default). Indicator lines persist while quotes update, and the RSI pane keeps a fixed 0–100 scale. Click an active indicator chip to remove it directly. Indicators use the bars shown by the selected chart range; missing time buckets are not fabricated. The latest intraday bar may still be forming. RSI is momentum context, not a guaranteed buy/sell signal.

Use **Level** and click an observed bar in the price pane, or **Trend** and click two different observed bars. Cancel/Esc stops drawing; Undo removes the last annotation; Clear removes annotations for that symbol after confirmation. Annotations are stored per instrument in this browser, not in the server account. They create no orders.

Trade reviews explain the actual direction of the price move, amount per unit, quantity and allocated charges, followed by concrete process checks. Future fills now save indicator context at entry and exit using only completed synthetic 10-second bars before execution. Snapshots require sufficient consecutive history (RSI14:15 bars, SMA10:10, EMA20:20); gaps restart warmup. This conservative review context differs from the chart, which counts observed bars across gaps and can show the forming bar. Older fills have no saved snapshot and are explicitly unavailable. Entry context belongs to the initial opening fill, even when later additions alter average cost. Indicator readings do not prove market causation or plan adherence; options use premium prices rather than the underlying.
