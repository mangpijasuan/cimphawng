#!/usr/bin/env node
/**
 * Private-beta ship gate: release fingerprint, backend suite, and the invited
 * member journey (demo-equivalent API path → trade → retry → export → logout → delete).
 * Owner-only gates (live D1 restore, monitoring, legal, domain, invites) remain manual.
 */
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {Wallet} from '../lib/ethers-server.mjs';
import {handleApi,SITE_ORIGIN} from '../lib/hosted-api.mjs';
import RELEASE from '../lib/release.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const hosted=path.join(root,'hosted');
const failures=[];

function step(name,fn){
 process.stdout.write(`• ${name}… `);
 try{fn();console.log('ok');}
 catch(error){failures.push(name+': '+(error.message||error));console.log('FAIL');console.error('  ',error.message||error);}
}

async function stepAsync(name,fn){
 process.stdout.write(`• ${name}… `);
 try{await fn();console.log('ok');}
 catch(error){failures.push(name+': '+(error.message||error));console.log('FAIL');console.error('  ',error.message||error);}
}

function run(command,args,cwd){
 const result=spawnSync(command,args,{cwd,encoding:'utf8'});
 if(result.status!==0)throw Error((result.stderr||result.stdout||'command failed').trim().slice(-800));
 return result.stdout;
}

step('release fingerprint',()=>{
 run(process.execPath,['hosted/scripts/release.mjs','--check'],root);
 if(RELEASE.version!=='0.2.0-beta.1'||RELEASE.channel!=='private-beta')throw Error('Unexpected release metadata');
});

step('backend test suite (21)',()=>{
 const out=run('npm',['test'],hosted);
 if(!out.includes('# pass 21')||out.includes('# fail')&&!out.includes('# fail 0'))throw Error(out.slice(-500));
});

function database(){
 const sqlite=new DatabaseSync(':memory:');
 const migration=fs.readdirSync(path.join(hosted,'drizzle')).filter(n=>n.endsWith('.sql')).sort()
  .map(n=>fs.readFileSync(path.join(hosted,'drizzle',n),'utf8')).join('\n');
 sqlite.exec(migration);
 return {
  prepare(sql){return {bind(...args){return statement(sql,args);},...statement(sql,[])};},
  async batch(statements){sqlite.exec('BEGIN');try{const results=statements.map(s=>s.syncRun());sqlite.exec('COMMIT');return results;}catch(e){sqlite.exec('ROLLBACK');throw e;}},
  sqlite
 };
 function statement(sql,args){const query=()=>sqlite.prepare(sql);return {
  async first(){return query().get(...args)||null;},
  async all(){return {results:query().all(...args)};},
  async run(){return this.syncRun();},
  syncRun(){const r=query().run(...args);return {meta:{changes:Number(r.changes)}};}
 };}
}

async function invitedBetaJourney(){
 const db=database();
 const fetcher=async url=>{
  const token=url.includes('0x420000')?'0x4200000000000000000000000000000000000006':'0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf';
  return Response.json({data:[{relationships:{base_token:{data:{id:'base_'+token}},quote_token:{data:{id:'base_0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'}}},attributes:{base_token_price_usd:token.startsWith('0x420')?'2000':'60000',reserve_in_usd:'1000000'}}]});
 };
 async function call(pathname,{method='GET',data,cookie,headers={}}={}){
  const r=await handleApi(new Request(SITE_ORIGIN+'/api'+pathname,{
   method,
   headers:{
    ...(data===undefined?{}:{'Content-Type':'application/json',Origin:SITE_ORIGIN}),
    ...(cookie?{Cookie:cookie}:{}),
    ...(/^\/paper\/(swap|reset)$/.test(pathname)?{'Idempotency-Key':crypto.randomUUID()}:{}),
    ...headers
   },
   ...(data===undefined?{}:{body:JSON.stringify(data)})
  }),db,{fetcher});
  return {r,status:r.status,body:await r.json()};
 }
 const health=await call('/health');
 if(health.status!==200||!health.body.ok)throw Error('health failed');
 const ready=await call('/ready');
 if(ready.status!==200||ready.body.status!=='ready')throw Error('ready not ready: '+JSON.stringify(ready.body));
 const release=await call('/release');
 if(release.body.fingerprint!==RELEASE.fingerprint)throw Error('live release fingerprint mismatch vs local');
 if((await call('/bot')).status!==501)throw Error('bot should be unsupported');

 const wallet=Wallet.createRandom();
 const nonce=await call('/auth/nonce?address='+wallet.address);
 if(nonce.status!==200)throw Error('nonce failed');
 const signature=await wallet.signMessage(nonce.body.message);
 const login=await call('/auth/verify',{method:'POST',data:{nonce:nonce.body.nonce,signature}});
 if(login.status!==200)throw Error('verify failed');
 const cookie=login.r.headers.get('Set-Cookie').split(';')[0];
 for(const flag of ['HttpOnly','Secure','SameSite=Lax'])if(!login.r.headers.get('Set-Cookie').includes(flag))throw Error('missing cookie flag '+flag);

 const paper=await call('/paper',{cookie});
 if(paper.body.total_usd!=='100.00')throw Error('expected starting portfolio');

 const key=crypto.randomUUID();
 const data={from_asset:'USDC',to_asset:'ETH',amount:'10'};
 const swap=await call('/paper/swap',{method:'POST',cookie,headers:{'Idempotency-Key':key},data});
 if(swap.status!==200)throw Error('swap failed '+swap.status);
 const retry=await call('/paper/swap',{method:'POST',cookie,headers:{'Idempotency-Key':key},data});
 if(!retry.body.replayed||retry.body.trade.id!==swap.body.trade.id)throw Error('retry did not replay');

 const exported=await call('/account/export',{cookie});
 if(exported.body.trades.length!==1||exported.body.account.address!==wallet.address.toLowerCase())throw Error('export incomplete');

 const signedOut=await call('/auth/logout',{method:'POST',cookie,data:{}});
 if(!signedOut.r.headers.get('Set-Cookie')?.includes('Max-Age=0'))throw Error('logout cookie not cleared');
 if((await call('/me',{cookie})).status!==401)throw Error('session still valid after logout');

 const againNonce=await call('/auth/nonce?address='+wallet.address);
 const againSig=await wallet.signMessage(againNonce.body.message);
 const again=await call('/auth/verify',{method:'POST',data:{nonce:againNonce.body.nonce,signature:againSig}});
 const againCookie=again.r.headers.get('Set-Cookie').split(';')[0];
 const deleted=await call('/account/delete',{method:'POST',cookie:againCookie,data:{confirmation:wallet.address}});
 if(deleted.status!==200)throw Error('delete failed '+deleted.status);
 if((await call('/me',{cookie:againCookie})).status!==401)throw Error('session survived deletion');
 db.sqlite.close();
}

await stepAsync('invited-beta API journey (sign-in → trade → retry → export → logout → delete)',invitedBetaJourney);

const betaPages=['guide.html','account.html','status.html','beta.css','account.js','status.js','index.html'];
step('beta surface assets present',()=>{
 for(const name of betaPages){
  const file=path.join(root,name);
  if(!fs.existsSync(file)||!fs.statSync(file).size)throw Error('missing '+name);
 }
});

step('clean beta URL aliases in worker and pages',()=>{
 const worker=fs.readFileSync(path.join(hosted,'worker.mjs'),'utf8');
 for(const route of ['/guide','/account','/status']){
  if(!worker.includes("'"+route+"'"))throw Error('worker missing alias '+route);
  const hits=[fs.readFileSync(path.join(root,'index.html'),'utf8'),fs.readFileSync(path.join(root,'guide.html'),'utf8')]
   .some(src=>src.includes('href="'+route+'"')||src.includes("href='"+route+"'"));
  if(!hits)throw Error('pages missing link to '+route);
 }
});

console.log('\nRelease '+RELEASE.version+' · '+RELEASE.fingerprint.slice(0,12)+'… · channel '+RELEASE.channel);
console.log('Site origin (SIWE): '+SITE_ORIGIN);
console.log('\nAutomated ship checks: '+(failures.length?'FAILED':'PASSED'));
if(failures.length){
 for(const f of failures)console.error('- '+f);
 process.exit(1);
}

console.log(`
Owner gates still required before public launch (see docs/LAUNCH-READINESS.md):
  [ ] Real-device wallet QA (EOA, cancel/reject, mobile, a11y)
  [ ] Invite a small beta cohort (access still owner-private; live Site returns 401 without audience)
  [ ] External monitor + ops owner for /api/health and /api/ready
  [ ] Hosting spend/error thresholds in the provider account
  [ ] Production D1 backup/restore rehearsal (local fixture restore is not enough)
  [ ] Legal/owner review of privacy + beta terms drafts
  [ ] Production domain + explicit audience decision
  [ ] Mainnet token kept as a separate decision
`);
