# Cimphawng Terminal

A hobby project: a sci-fi "trading bot terminal" dashboard for the fictional **CIM** token,
inspired by the neon HFT dashboards floating around on X.

**Everything is simulated.** Prices come from a random walk that runs in your browser.
No real market, wallet, API or money is involved. Not financial advice.

## What it shows

The bot plays a made-up 1-minute **CIM UP/DOWN** prediction market. Each share pays $1 if its
side wins. When `UP ask + DOWN ask < $1`, buying one of each (a "complete set") locks in the gap
as profit whatever the outcome. That's the game the bot plays:

| Panel | What it is |
|---|---|
| My wallet | **Your** pretend $100: buy/sell CIM (Cimphawng Token) at the live price, or let the bot trade for you |
| Bot wallet | All-time PnL, trade stats, win rate, equity curve, per-round results |
| Transport matrix | UP/DOWN shares bought across the current round, in 5-second buckets |
| FIFO arc lace | Each completed set drawn as an arc linking its UP leg to its DOWN leg |
| CIM spot | 1-second candles, the round's opening price, and a simulated order book |
| Neural shell | Model inputs → rotating particle "brain" → order-router outputs (eye candy driven by live values) |
| Resolution funnel | Price path this round plus the ±1σ/±2σ volatility cone to settlement |
| Running combined VWAP | Cost of every recent set vs the $1.00 payout, with the running average |

## My wallet ($100 pretend mode)

- You start with **$100 of play money** and 0 CIM.
- **Buy $10 / $25 / all** and **Sell 25% / 50% / all** trade CIM at the current simulated price
  (you pay a tiny spread, like a real exchange).
- **Let bot trade my cash** copies 10% of every bot trade using your cash. That money is locked
  until the 1-minute round settles, then comes back with the win or loss.
- Your wallet is saved in your browser (localStorage), so it's still there when you come back.
  If you reload mid-round, open bot trades are refunded at cost.
- **Reset to $100** starts over.

The `1×` button in the header cycles the simulation speed through 1×, 4× and 16×.

## Run it

It's a single file with no build step:

- Open `index.html` in any browser, or
- Serve it: `python3 -m http.server` then visit http://localhost:8000, or
- Host it free with GitHub Pages (Settings → Pages → deploy from branch, root folder).
