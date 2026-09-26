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
