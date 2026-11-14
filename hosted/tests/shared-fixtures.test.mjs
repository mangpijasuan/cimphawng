// The same swaps the Python server runs (server/tests/test_shared_fixtures.py), from shared/paper-fixtures.json.
// Both backends must end every case exactly as the fixture says, so a fill never depends on which one served it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import fs from 'node:fs';
import {Wallet} from '../lib/ethers-server.mjs';
import {handleApi,SITE_ORIGIN} from '../lib/hosted-api.mjs';

const FIXTURES=JSON.parse(fs.readFileSync(new URL('../../shared/paper-fixtures.json',import.meta.url),'utf8'));
const migration=fs.readdirSync(new URL('../drizzle/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort().map(n=>fs.readFileSync(new URL('../drizzle/'+n,import.meta.url),'utf8')).join('\n');
function database(){const sqlite=new DatabaseSync(':memory:');sqlite.exec(migration);return {sqlite,
 prepare(sql){return {bind(...args){return statement(sql,args);},...statement(sql,[])};},
 async batch(statements){sqlite.exec('BEGIN');try{const results=statements.map(s=>s.syncRun());sqlite.exec('COMMIT');return results;}catch(e){sqlite.exec('ROLLBACK');throw e;}}};
 function statement(sql,args){const query=()=>sqlite.prepare(sql);return {async first(){return query().get(...args)||null;},async all(){return {results:query().all(...args)};},async run(){return this.syncRun();},syncRun(){const r=query().run(...args);return {meta:{changes:Number(r.changes)}};}};}}

for(const c of FIXTURES.cases){
 test('shared fixture: '+c.name,async t=>{
  const db=database();t.after(()=>db.sqlite.close());
  const prices={...FIXTURES.prices,...c.prices},time=Date.now();
  const fetcher=async url=>{const eth=url.includes('0x420000'),token=eth?'0x4200000000000000000000000000000000000006':'0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf';
   return Response.json({data:[{relationships:{base_token:{data:{id:'base_'+token}},quote_token:{data:{id:'base_0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'}}},attributes:{base_token_price_usd:eth?prices.ETH:prices.cbBTC,reserve_in_usd:'1000000'}}]});};
  const call=async(path,{method='GET',data,cookie,headers={}}={})=>{const r=await handleApi(new Request(SITE_ORIGIN+'/api'+path,{method,headers:{...(data===undefined?{}:{'Content-Type':'application/json',Origin:SITE_ORIGIN}),...(cookie?{Cookie:cookie}:{}),...headers},...(data===undefined?{}:{body:JSON.stringify(data)})}),db,{clock:()=>time,fetcher});return {status:r.status,headers:r.headers,body:await r.json()};};
  const wallet=Wallet.createRandom(),nonce=await call('/auth/nonce?address='+wallet.address);
  const login=await call('/auth/verify',{method:'POST',data:{nonce:nonce.body.nonce,signature:await wallet.signMessage(nonce.body.message)}});
  const cookie=login.headers.get('Set-Cookie').split(';')[0];
  await call('/paper',{cookie}); // fetches the prices and creates the account
  db.sqlite.prepare('UPDATE accounts SET balances=?').run(JSON.stringify(c.balances||FIXTURES.start));

  const expect=c.expect,allowed=Array.isArray(expect.status)?expect.status:[expect.status];
  const r=await call('/paper/swap',{method:'POST',cookie,data:{from_asset:c.from,to_asset:c.to,amount:c.amount},headers:{'Idempotency-Key':crypto.randomUUID()}});
  assert.ok(allowed.includes(r.status),'status '+r.status+' '+JSON.stringify(r.body));
  if(r.status===200)for(const field of ['amount_out','fee_usd','price_in_usd','price_out_usd'])assert.equal(r.body.trade[field],expect[field],field);
  const portfolio=await call('/paper',{cookie});
  assert.deepEqual(Object.fromEntries(portfolio.body.balances.map(b=>[b.asset,b.amount])),expect.balances);
  assert.equal((await call('/paper/trades',{cookie})).body.trades.length,expect.trades);
 });
}
