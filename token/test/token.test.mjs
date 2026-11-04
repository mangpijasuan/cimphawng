import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ganache from 'ganache';
import { BrowserProvider, ContractFactory, ZeroAddress, parseUnits } from 'ethers';
const artifact = JSON.parse(fs.readFileSync(new URL('../web/CimphawngTestToken.json', import.meta.url)));
async function fixture(t, chainId = 84532) {
  const raw = ganache.provider({ chain:{chainId, hardfork:'shanghai'}, logging:{quiet:true}, wallet:{totalAccounts:3} });
  t.after(() => raw.disconnect());
  const provider = new BrowserProvider(raw, undefined, { cacheTimeout: -1 });
  const owner = await provider.getSigner(0), other = await provider.getSigner(1), spender = await provider.getSigner(2);
  return {raw, provider, owner, other, spender, factory:new ContractFactory(artifact.abi,artifact.bytecode,owner)};
}
async function deployed(t, chainId) {
  const f = await fixture(t,chainId);
  f.token = await f.factory.deploy(await f.owner.getAddress()); await f.token.waitForDeployment();
  return f;
}
test('Base Sepolia: exact fixed supply, metadata, and runtime artifact', async t => {
  const {token,owner,provider} = await deployed(t);
  assert.equal(await token.name(),'Cimphawng Test Token'); assert.equal(await token.symbol(),'CIMP'); assert.equal(await token.decimals(),18n);
  const supply = parseUnits('1000000',18);
  assert.equal(await token.totalSupply(),supply); assert.equal(await token.balanceOf(await owner.getAddress()),supply);
  assert.equal(await provider.getCode(await token.getAddress()),artifact.deployedBytecode);
  for (const name of ['mint','owner','upgradeTo','pause','blacklist']) assert.equal(token.interface.getFunction(name),null);
});
for (const id of [31337,1337]) test(`local development chain ${id} can deploy`, async t => { await deployed(t,id); });
for (const id of [8453,1,11155111]) test(`deployment rejected on unsupported chain ${id}`, async t => {
  const {factory,owner} = await fixture(t,id);
  await assert.rejects(factory.deploy(await owner.getAddress()));
});
test('zero recipient deployment rejected', async t => { const {factory} = await fixture(t); await assert.rejects(factory.deploy(ZeroAddress)); });
test('transfer conserves supply and emits expected event without tax', async t => {
  const {token,owner,other} = await deployed(t); const from=await owner.getAddress(),to=await other.getAddress(),value=parseUnits('12.345',18);
  const receipt = await (await token.transfer(to,value)).wait();
  const log = receipt.logs.map(log=>token.interface.parseLog(log)).find(log=>log.name==='Transfer');
  assert.equal(log.args[0],from); assert.equal(log.args[1],to); assert.equal(log.args[2],value);
  assert.equal(await token.balanceOf(to),value); assert.equal(await token.balanceOf(from),parseUnits('1000000',18)-value);
  assert.equal(await token.totalSupply(),parseUnits('1000000',18));
});
test('insufficient balance and zero address transfers rejected', async t => {
  const {token,other} = await deployed(t);
  await assert.rejects(token.connect(other).transfer(await token.runner.getAddress(),1n));
  await assert.rejects(token.transfer(ZeroAddress,1n));
});
test('delegated transfer needs allowance and decrements it', async t => {
  const {token,owner,other,spender} = await deployed(t); const from=await owner.getAddress(),to=await other.getAddress(),delegate=await spender.getAddress();
  await assert.rejects(token.connect(spender).transferFrom(from,to,3n));
  await (await token.approve(delegate,10n)).wait(); await (await token.connect(spender).transferFrom(from,to,3n)).wait();
  assert.equal(await token.allowance(from,delegate),7n); assert.equal(await token.balanceOf(to),3n);
});
