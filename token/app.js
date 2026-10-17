/* global ethers */
'use strict';
const $ = id => document.getElementById(id);
const CHAIN = '0x14a34';
const STORE = 'cimphawng-testnet-contract-84532-v1';
let raw, provider, account, artifact, tokenAddress, busy = false, epoch = 0;
let lang = 'zo';
try { lang = localStorage.getItem('cimphawng-lang') === 'en' ? 'en' : 'zo'; } catch {}
const english = {
  back:'← Cimphawng Home', intro:'Explore an actual blockchain token using test funds. Connect your wallet, deploy or load CIMP, check your balance, and send test tokens.',
  test:'Testing only · No monetary value', separate:'Separate from simulated CIMP and paper USDC. No real-money trading, market price, liquidity, or promised returns.',
  wallet:'1. Wallet', keys:'Approve actions in your wallet. We never ask for a seed phrase or private key.', connect:'Connect wallet', switch:'Switch to Base Sepolia',
  token:'2. Test token', supply:'Fixed supply. No additional minting, tax, blacklist, admin key, or upgrades. All initial tokens go to the deploying wallet.',
  deployTitle:'Deploy a test token', deployInfo:'This creates a NEW token. You need Base Sepolia test ETH for gas. Deploy once; others can use the same contract address.',
  ack:'I understand this creates a new testnet token.', deploy:'Deploy 1,000,000 test CIMP', attachTitle:'Use an existing test token', address:'Base Sepolia contract address', attach:'Verify & load',
  verify:'Checks contract code and supply before loading. Reading an address does not transfer tokens.', balance:'3. Balance & transfer', refresh:'Refresh balance',
  recipient:'Recipient wallet address', amount:'Test CIMP amount (up to 18 decimals)', transferInfo:'Send test CIMP only. Check the recipient and amount in your wallet. Transfers use test ETH for gas.',
  transfer:'Review transfer in wallet', activity:'Activity'
};
const zomi = {};
for (const el of document.querySelectorAll('[data-i18n]')) zomi[el.dataset.i18n] = el.textContent;
function renderLanguage() {
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = (lang === 'en' ? english : zomi)[el.dataset.i18n];
  $('language').textContent = lang === 'en' ? 'Zomi' : 'English';
}
$('language').onclick = () => { lang = lang === 'en' ? 'zo' : 'en'; try { localStorage.setItem('cimphawng-lang', lang); } catch {} renderLanguage(); };
renderLanguage();
function status(message) { $('status').textContent = message; }
function controls() {
  const ready = !!account && $('network').dataset.ready === 'true' && !!artifact;
  for (const id of ['connect','switch']) $(id).disabled = busy;
  $('deploy').disabled = busy || !ready || !$('ack').checked;
  $('attach').disabled = busy || !ready;
  for (const id of ['refresh','transfer']) $(id).disabled = busy || !ready || !tokenAddress;
}
function reset() { epoch++; tokenAddress = null; $('contract').textContent = 'Not deployed / not selected'; $('balance').textContent = '— CIMP'; $('tx').hidden = true; }
async function networkState() {
  const chain = await raw.request({ method:'eth_chainId' });
  $('network').textContent = chain === CHAIN ? 'Base Sepolia (testnet)' : `Wrong network (${chain}). Base Sepolia required.`;
  $('network').dataset.ready = String(chain === CHAIN);
  $('switch').hidden = chain === CHAIN;
  controls();
}
async function checkedSigner(turn) {
  if (!raw || !account || turn !== epoch) throw Error('Wallet changed. Reconnect and review again.');
  if (await raw.request({ method:'eth_chainId' }) !== CHAIN) throw Error('Base Sepolia required. Mainnet is disabled.');
  const accounts = await raw.request({ method:'eth_accounts' });
  if (accounts[0]?.toLowerCase() !== account.toLowerCase() || turn !== epoch) throw Error('Wallet changed. Reconnect and review again.');
  return provider.getSigner(account);
}
async function run(fn) {
  if (busy) return;
  busy = true; controls();
  try { await fn(epoch); }
  catch (err) { status(err.shortMessage || err.message || 'Wallet request failed.'); }
  finally { busy = false; controls(); }
}
function txLink(hash) { const el = $('tx'); el.href = `https://sepolia.basescan.org/tx/${hash}`; el.textContent = `View testnet transaction: ${hash}`; el.hidden = false; }
async function balance(turn) {
  await checkedSigner(turn);
  const value = await new ethers.Contract(tokenAddress, artifact.abi, provider).balanceOf(account);
  if (turn !== epoch) throw Error('Wallet changed. Reconnect.');
  $('balance').textContent = `${ethers.formatUnits(value, 18)} CIMP`;
}
async function load(address, turn) {
  await checkedSigner(turn);
  address = ethers.getAddress(address);
  const code = await provider.getCode(address);
  if (code.toLowerCase() !== artifact.deployedBytecode.toLowerCase()) throw Error('Contract does not match this test token build.');
  const contract = new ethers.Contract(address, artifact.abi, provider);
  if (await contract.totalSupply() !== ethers.parseUnits('1000000',18)) throw Error('Unexpected test token supply.');
  if (turn !== epoch) throw Error('Wallet changed. Reconnect.');
  tokenAddress = address;
  $('contract').replaceChildren();
  const a = document.createElement('a'); a.href = `https://sepolia.basescan.org/address/${address}`; a.textContent = address; a.target = '_blank'; a.rel = 'noopener noreferrer'; $('contract').append(a);
  $('address').value = address;
  try { localStorage.setItem(STORE, address); } catch {}
  await balance(turn);
}
$('ack').onchange = controls;
$('connect').onclick = () => run(async () => {
  if (!window.ethereum) throw Error('Open this page in a browser wallet or install a wallet extension.');
  if (raw?.removeListener) { raw.removeListener('accountsChanged', changed); raw.removeListener('chainChanged', changed); raw.removeListener('disconnect', changed); }
  raw = window.ethereum;
  reset();
  const accounts = await raw.request({ method:'eth_requestAccounts' });
  if (!accounts.length) throw Error('No wallet account selected.');
  account = ethers.getAddress(accounts[0]); provider = new ethers.BrowserProvider(raw);
  $('account').textContent = account;
  raw.on?.('accountsChanged', changed); raw.on?.('chainChanged', changed); raw.on?.('disconnect', changed);
  await networkState();
  status('Wallet connected. Only Base Sepolia test transactions are supported.');
  if ($('network').dataset.ready === 'true') {
    let saved; try { saved = localStorage.getItem(STORE); } catch {}
    if (saved) { await load(saved, epoch); status('Previously selected test contract verified and loaded.'); }
  }
});
function changed() {
  reset(); account = null; provider = null; $('account').textContent = 'Reconnect wallet'; $('network').dataset.ready = 'false'; $('network').textContent = 'Wallet changed — reconnect';
  status('Wallet account or network changed. Reconnect before continuing.'); controls();
}
$('switch').onclick = () => run(async () => {
  try { await raw.request({ method:'wallet_switchEthereumChain', params:[{ chainId:CHAIN }] }); }
  catch (err) {
    if (err.code !== 4902) throw err;
    await raw.request({ method:'wallet_addEthereumChain', params:[{ chainId:CHAIN, chainName:'Base Sepolia', nativeCurrency:{name:'Ether',symbol:'ETH',decimals:18}, rpcUrls:['https://sepolia.base.org'], blockExplorerUrls:['https://sepolia.basescan.org'] }] });
  }
  changed();
});
$('deploy').onclick = () => run(async turn => {
  if (!$('ack').checked) throw Error('Confirm the testnet deployment checkbox first.');
  const signer = await checkedSigner(turn);
  const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode, signer);
  status('Review deployment in your wallet: NEW test token; 1,000,000 CIMP to your account. Uses Base Sepolia test ETH for gas.');
  const contract = await factory.deploy(account, { chainId:84532 });
  const hash = contract.deploymentTransaction().hash;
  txLink(hash); status('Deployment submitted. Waiting for confirmation. Keep this transaction link if you leave the page.');
  await contract.waitForDeployment();
  if (turn !== epoch) throw Error(`Deployment submitted: ${hash}. Reconnect to load its contract.`);
  await load(await contract.getAddress(), turn); $('ack').checked = false;
  status('Test token deployed and verified. Share this contract address with testers. No mainnet token or trading pool was created.');
});
$('attach').onclick = () => run(async turn => { await load($('address').value.trim(), turn); status('Test contract verified and loaded.'); });
$('refresh').onclick = () => run(async turn => { $('balance').textContent = 'Refreshing…'; await balance(turn); status('Balance refreshed from Base Sepolia.'); });
$('transferForm').onsubmit = event => { event.preventDefault(); run(async turn => {
  const signer = await checkedSigner(turn);
  if (!tokenAddress) throw Error('Load a verified test token first.');
  const to = ethers.getAddress($('recipient').value.trim());
  if (to === ethers.ZeroAddress) throw Error('Recipient cannot be the zero address.');
  const text = $('amount').value.trim();
  if (!/^\d+(\.\d{1,18})?$/.test(text)) throw Error('Enter a positive amount with at most 18 decimal places.');
  const value = ethers.parseUnits(text,18);
  if (value <= 0n) throw Error('Amount must be greater than zero.');
  const contract = new ethers.Contract(tokenAddress, artifact.abi, signer);
  if (value > await contract.balanceOf(account)) throw Error('Insufficient test CIMP balance.');
  await checkedSigner(turn);
  status(`Review in wallet: send ${ethers.formatUnits(value,18)} test CIMP to ${to}. Test ETH gas required.`);
  const tx = await contract.transfer(to, value, {chainId:84532}); txLink(tx.hash); status('Transfer submitted. Waiting for confirmation.');
  await tx.wait(); await balance(turn); status('Test CIMP transfer confirmed.');
}); };
fetch('web/CimphawngTestToken.json').then(r => { if (!r.ok) throw Error('Missing token build. Run npm ci and npm run build in token/.'); return r.json(); }).then(value => {
  if (!window.ethers || value.chainId !== 84532 || !value.bytecode || !value.deployedBytecode) throw Error('Invalid test token build.');
  artifact = value; controls();
}).catch(err => status(err.message));
controls();
