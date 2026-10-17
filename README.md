# Cimphawng Terminal

A hobby project: a sci-fi "trading bot terminal" dashboard for the fictional **CIMP** token,
inspired by the neon HFT dashboards floating around on X.

**Everything is simulated.** Prices come from a random walk that runs in your browser.
No real market, wallet, API or money is involved. Not financial advice.

## What it shows

The bot plays a made-up 1-minute **CIMP UP/DOWN** prediction market. Each share pays $1 if its
side wins. When `UP ask + DOWN ask < $1`, buying one of each (a "complete set") locks in the gap
as profit whatever the outcome. That's the game the bot plays:

| Panel | What it is |
|---|---|
| My wallet | **Your** pretend $100: buy/sell CIMP (Cimphawng Token) at the live price, or let the bot trade for you |
| Bot wallet | All-time PnL, trade stats, win rate, equity curve, per-round results |
| Transport matrix | UP/DOWN shares bought across the current round, in 5-second buckets |
| FIFO arc lace | Each completed set drawn as an arc linking its UP leg to its DOWN leg |
| CIMP spot | 1-second candles, the round's opening price, and a simulated order book |
| Neural shell | Model inputs → rotating particle "brain" → order-router outputs (eye candy driven by live values) |
| Resolution funnel | Price path this round plus the ±1σ/±2σ volatility cone to settlement |
| Running combined VWAP | Cost of every recent set vs the $1.00 payout, with the running average |

## My wallet ($100 pretend mode)

- You start with **$100 of play money** and 0 CIMP.
- **Buy $10 / $25 / all** and **Sell 25% / 50% / all** trade CIMP at the current simulated price
  (you pay a tiny spread, like a real exchange).
- **Let bot trade my cash** copies 10% of every bot trade using your cash. That money is locked
  until the 1-minute round settles, then comes back with the win or loss.
- Your wallet is saved in your browser (localStorage), so it's still there when you come back.
  If you reload mid-round, open bot trades are refunded at cost.
- **Reset to $100** starts over.

## Phone view

On phones (screens up to 760px wide) the terminal turns into an app-style layout:

- **Top chips:** your pretend wallet total, the live ETH price and the CIMP price. Tap a chip to jump to its tab.
- **Rounded cards** for every stat and button, in a softer font.
- **A floating tab bar** with five screens:

| Tab | Shows |
|---|---|
| **Inn** (Home) | Your $100 pretend wallet |
| **Market** | Real Base DEX prices (ETH, cbBTC) |
| **CIMP** | The simulated CIMP price, order book and round |
| **Bot** | The bot's wallet and trading charts |
| **AI** | The neural-shell animation |

Only the open tab's charts are drawn, which saves battery. The app remembers the last tab you used. Desktop keeps the full terminal.

## Perps Desk (paper-only learning lab): `desk.html`

A separate page for researching a high-leverage perpetual-futures plan on BTC, ETH, SOL, AVAX and SUI, using
Hyperliquid's free public market data. **Paper only:** the page has no exchange key or wallet and cannot place real orders.

Every 60 seconds it:

- **Scans the five coins:** price, 1h/4h/24h change, funding, open interest, order-book depth.
- **Estimates each coin's expected move** over the next ~4 hours: 1h ATR(14) × 2.
- **Applies the hard rule:** leverage ≈ target return on margin ÷ expected move (default target 100%). A smaller
  expected move gives higher leverage. It never goes above 30x, prefers 26x or less, and never exceeds the coin's own maximum.
- **Applies the other rules:**
  - Trade only with the coin's short-term bias and the board's lean (shorts on a red day).
  - 50% of equity as margin per trade, and at most 70% of equity in margin in total.
  - Skip if slippage would be over 0.3%.
  - Take-profit at the expected move, stop-loss at ⅓ of it.
  - The stop must sit well inside the liquidation price, or leverage is lowered.
- **Writes tickets with IDs.** Each shows entry, TP, SL, the approximate liquidation price, profit or loss on margin at TP and SL,
  and **how much of the stack it risks**. A ticket only fills (on paper) when you press **Approve**, and expires after 5 minutes.
- **Watches open positions** every 10 seconds and closes the whole position at TP or SL.
- **Safety guards** (the same kind as the architecture's bot guards):
  - A **daily loss limit**: default 20%, then no new tickets until the next UTC day.
  - A stop after **3 losses in a row**.
  - A **kill switch** that closes every paper position at market and stops new tickets until **Resume**.

Paper results aim to be honest rather than flattering:
- Approvals fill at a fresh price.
- Exits missed while the page was closed are replayed from 1-minute candles.
- A liquidation counts as losing the whole margin.
- Fees use the rate in force when the trade was opened.

It's an official Cimphawng feature (see section 8 of `docs/ARCHITECTURE.md`): a **paper-only learning lab**, linked from the
**Bot** tab with a risk warning, in Zomi or English. A live version would be owner-only and never use members' money.

The dashboard shows equity against the starting $53, open positions, a trade grid, top closes, running stats
(win rate, fees, max drawdown, average win and loss) and a full decision log. Everything is stored in your browser.
High leverage can wipe out a trade's margin in a small move. Not financial advice.

## Base DEX live prices (real data)

The **Base DEX** panel shows **real** prices for **ETH** and **cbBTC** in US dollars, from their most active
USDC pool on the Base blockchain (for example Uniswap or Aerodrome):

- Price, 24h change, 24h volume and pool liquidity for each coin, plus ETH in the header
- A candlestick chart with volume, with 5m / 15m / 1h / 4h / 1D timeframes
- The latest trades in the pool, each linked to the transaction on BaseScan
- A link to the pool on GeckoTerminal

Data comes from the free public [GeckoTerminal API](https://www.geckoterminal.com/dex-api), with DexScreener as a backup for
prices. Pools are found automatically and remembered for a day. The page makes about 5 requests a minute (the free
limit is about 30), pauses while the tab is hidden, and backs off and retries if the service is down or busy.
**It's read-only: nothing here trades or connects a wallet.** The CIMP simulation is unchanged.

## Analysis (learning only, not advice)

Under the Base DEX chart:

- **Moving averages** on the chart: MA20 (yellow) and MA50 (cyan), the average price of the last 20 and 50 candles.
- **RSI 14** below the chart. Above 70 means the price rose fast (overbought); below 30 means it fell fast (oversold).
- **Signal cards** in Zomi or English:
  - **Trend:** is the price above or below both averages?
  - **RSI:** overbought, oversold or neutral.
  - **Volatility:** the typical daily move, labelled calm, normal or wild.
  - **Golden or death cross:** shown when MA20 has just crossed MA50.
- **Backtest:** runs a pretend $100 over the chart's history (up to 300 candles) with one of two simple strategies:
  - **MA cross:** buy when MA20 crosses above MA50, sell when it crosses below.
  - **RSI 30/70:** buy when RSI drops below 30, sell when it rises above 70.

  It charges a 0.3% fee per swap, trades at the next candle's open (so it never uses future prices), and compares
  the result with simply buying and holding. It shows the final value, return, number of trades, win rate and biggest drop.

Everything here is for learning. Past results don't predict the future.

## Price news

Every minute or two, a news headline pops up in a banner under the live feed. Good news (green ▲),
like "Cimphawng listed on a new exchange", pushes CIMP up. Bad news (red ▼), like "A whale dumps 2M CIMP",
pushes it down. The move plays out over 6–12 seconds, so you have a few seconds to buy or sell with your
pretend wallet. It's a small (3–7%) or big (7–12%) move, and part of it fades over the next few minutes.
News candles are marked with an **N** on the CIMP price chart, and headlines also appear in the live feed.

## Zomi / English

The page opens in **Zomi**. The **English** / **Zomi** button in the header switches language,
and your choice is remembered. All the Zomi words live in one list, `const ZO = { ... }`, near the
top of the `<script>` in `index.html`. The English text is on the left and the Zomi on the right, so fixing
a word is just editing the right-hand side. Keep any `{name}` parts, because numbers are filled in there.
Trading jargon (VWAP, FIFO, UP/DOWN, set, leg, tilt) stays in English on purpose.

The `1×` button in the header cycles the simulation speed through 1×, 4× and 16×.

## Server and paper trading (step 3, in progress)

The `server/` folder holds the Python API that will run on Hetzner at cimphawng.com:

- **Wallet sign-in** (Sign-In with Ethereum). Members sign a free message in their own wallet. The server never sees keys.
- **Paper trading** for every member: 100 pretend USDC to swap between USDC, ETH and cbBTC at **real** Base DEX prices, with a 0.3% fee.

`infra/` has the Docker Compose, Caddy (automatic HTTPS) and PostgreSQL setup. See [server/README.md](server/README.md)
for the API, and [docs/DEPLOY.md](docs/DEPLOY.md) for step-by-step Hetzner setup.

The web page's **Paper trading** panel (on the Home / Inn tab) uses the server:

- **Connect wallet:** sign in with MetaMask, Coinbase Wallet, Rabby or any wallet with a browser extension or in-app browser.
- See your pretend portfolio, swap with a live "you get about…" preview, see your last trades, reset, and sign out.
- It says clearly that Cimphawng never asks for a seed phrase, and that signing in is free.

On GitHub Pages there's no server, so the panel just says paper trading starts once cimphawng.com is live.

The **System** panel on the AI tab shows live numbers from the server, all real and none personal, refreshed every 5 seconds while it's on screen:

- **Server:** uptime, memory, CPU load.
- **Community:** members, members active in the last 24 hours, paper trades today.
- **API traffic:** requests per minute, errors and response times.
- **Price feed:** the age of each price, plus successful and failed refreshes.
- **Database:** ping and size.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the app works today and the planned design:
real DEX prices (starting on Base), analysis, wallet sign-in for the Zomi community, paper trading and,
later, automated trading, all on a Hetzner server at cimphawng.com. It's non-custodial: members always
keep and sign for their own coins.

## Run it

It's a single file with no build step:

- Open `index.html` in any browser, or
- Serve it: `python3 -m http.server` then visit http://localhost:8000, or
- Host it free with GitHub Pages (Settings → Pages → deploy from branch, root folder).

## CIMP Testnet Lab

Open [token/](token/) from the Home wallet card to deploy or load a **Cimphawng Test Token**
on **Base Sepolia (chain 84532)**. This is a separate experimental ERC-20 with a provisional
fixed supply of 1,000,000 test CIMP, minted once to the deploying wallet. The contract blocks
mainnet deployment. No token is deployed just by opening the page or merging this code.

The lab checks the selected contract's runtime bytecode and supply before showing its balance
or enabling transfers. Deployment and transfers require the user's own browser wallet approval
and Base Sepolia test ETH for gas. It never asks for a private key or seed phrase.

**Simulation balances, paper balances, and simulated bot profits cannot be redeemed for test tokens.**
No price, liquidity pool, rewards entitlement, or mainnet tokenomics is introduced.
See [the deployment guide](docs/CIMP-TESTNET.md) for testing, deployment, and verification.
