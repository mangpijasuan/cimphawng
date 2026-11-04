# CIMP Testnet Lab

## What is ready

- `token/contracts/CimphawngTestToken.sol`: OpenZeppelin ERC-20, Solidity 0.8.30.
- Name **Cimphawng Test Token**, symbol **CIMP**, 18 decimals.
- **1,000,000 test CIMP**, minted once to the constructor recipient; the browser uses the deploying account.
- No additional mint, admin, pause, blacklist, transfer tax, upgrade, staking, redemption, or sales mechanism.
- Constructor allows only Base Sepolia (84532) and local development chains (31337, 1337).
- Separate Zomi/English wallet page, linked from Home. Technical wallet status messages remain English.
- Wallet connection, explicit network switch, deployment, exact-bytecode contract selection, balance, and transfer.
- No contract address is prepopulated because no public deployment has been performed.

This is testing infrastructure, not a mainnet launch. Supply is provisional, not a future distribution promise.
Each deployment has its own address and balances. Sharing the same symbol does not make two contracts the same token.
The existing random-walk CIMP market, pretend $100 wallet, paper trades, and bot profits remain simulations;
they cannot be converted or redeemed. Test CIMP has no claimed monetary value or guaranteed access benefits.

## Build and test

Use Node.js 22 LTS and npm:

```sh
cd token
npm ci
npm test
```

`npm test` compiles the contract and runs actual local EVM tests. `npm run build` updates:

- `web/CimphawngTestToken.json`: ABI, creation bytecode, exact runtime bytecode, compiler and chain.
- `web/standard-input.json`: all Solidity sources plus compiler settings for explorer verification.
- Local browser ethers library and license. The page does not load wallet code from a CDN.

Commit these generated files whenever the contract or dependency lock changes. A different build may fail
runtime verification for previously deployed addresses, so preserve the build used for each deployment.
Compiler optimizer is enabled at 200 runs; EVM version is Paris.

For the browser end-to-end test:

```sh
npx playwright install chromium
npm run test:browser
```

Tests run with an ephemeral local blockchain and test accounts, never a real wallet or public chain.

## Serve the page

From the repository root:

```sh
python3 -m http.server 8000
```

Open `http://localhost:8000/token/`. Alternatively use the existing static site host after merging.
Do not open via `file://`; artifact loading needs HTTP. If the production host uses an explicit static
file allowlist, include `token/` and all `token/web/` assets. No backend migration is required.

## Deploy once on Base Sepolia

1. Open the page with a wallet extension or the wallet's in-app browser. Use a separate testing wallet.
2. Click **Connect wallet**. This requests account access only; it does not ask for a sign-in signature.
3. Click **Switch to Base Sepolia** if prompted, approve the network request, then reconnect.
   Network: chain ID **84532**, RPC `https://sepolia.base.org`, explorer `https://sepolia.basescan.org`.
   Check these against [Base's official network details](https://docs.base.org/get-started/connect-to-base).
4. Obtain **Base Sepolia test ETH** using a faucet linked from the official Base documentation.
   Ethereum Sepolia ETH and mainnet ETH are different assets. The lab does not require buying tokens.
5. Check the testnet acknowledgment and click **Deploy 1,000,000 test CIMP**.
6. Review the deployment and estimated gas in your wallet. Approve only on Base Sepolia.
7. Wait for confirmation. Save the **contract address** and **transaction hash** shown on the page.
   The initial supply belongs to your deploying wallet. No public faucet or automatic airdrop exists.
8. Publish the confirmed testnet address and deployment transaction in this guide in a follow-up change.
   Never publish a seed phrase, private key, or keystore.

The page remembers the selected address on this browser only, and re-verifies it on connection.
If the page closes or a wallet changes during deployment, recover the address from the transaction on
Base Sepolia's explorer, reconnect, and paste it under **Use an existing test token**. Do not deploy again
just because a page was reloaded. A rejected wallet prompt or an RPC error does not prove a previously
submitted transaction was cancelled: check its hash first.

## Other testers and transfers

Share the confirmed **chain + contract address**, not just the name. A tester connects on Base Sepolia,
pastes that address, and presses **Verify & load**. Verification checks exact deployed code and total
supply against this repository's build. Different or empty contracts are rejected. This is a build match,
not a third-party security audit.

The deployer can send a small amount to each tester using the transfer form. Testers need test ETH to
send tokens themselves. Transfers have no token tax; the network still charges test ETH gas. Every
transfer requires a wallet confirmation. This page never requests token spending approvals.

Wallet account/network changes invalidate the current selection and require reconnection. Mainnet
writes are disabled in the UI and rejected by the contract constructor. Connect uses the browser's
injected wallet; a dedicated multi-wallet picker and WalletConnect are not implemented.

## Explorer source verification

After deployment, open the contract address on Base Sepolia BaseScan and use **Verify and Publish**.
Select Solidity Standard JSON Input, compiler **v0.8.30+commit.73712a01**, MIT license, and upload
`token/web/standard-input.json`. Use contract `CimphawngTestToken.sol:CimphawngTestToken`.
The constructor argument is the deploying wallet address encoded as one ABI `address` (32-byte word).
The standard input already includes the optimizer and EVM settings. Verify with the exact committed
build used to deploy; compare compiler version with the artifact if rebuilding with different tooling.

## Before considering mainnet

Define an actual user benefit, distribution and vesting rules, treasury controls, security review,
and obtain advice appropriate to the intended offering and users. A mainnet design requires a separate
contract and explicit launch decision; removing this testnet guard is not a complete launch plan.
A token contract alone creates neither an exchange market nor liquidity nor business revenue.
