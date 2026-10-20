import RELEASE from './release.mjs';
import { getAddress, verifyMessage, parseUnits, formatUnits } from './ethers-server.mjs';
const SCALE=10n**18n;
const ASSETS=['USDC','ETH','cbBTC'];
export const FEATURES={wallet_signin:true,paper_trading:true,paper_bots:false,real_trading:false,testnet_lab:true,idempotency:true,account_export:true,account_delete:true};
const TOKENS={ETH:'0x4200000000000000000000000000000000000006',cbBTC:'0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf'};
const USDC='base_0x833589fcd6edb6e08f4c7c32d4f71b54bda02913';
export const SITE_ORIGIN='https://cimphawng-lab-preview.neat-tetra-8078.chatgpt.site';
const initial=()=>({USDC:'100',ETH:'0',cbBTC:'0'});
const fmt=x=>formatUnits(x,18).replace(/\.0$/,'');
function fail(status,message){throw Object.assign(new Error(message),{status});}
function units(value){if(typeof value!=='string'||!/^\d{1,22}(\.\d{1,18})?$/.test(value))fail(400,'Use a positive decimal amount with at most 18 decimal places.');return parseUnits(value,18);}
const json=(data,status=200,headers={})=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',...headers}});
const random=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
async function hash(value){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('');}
async function rate(db,key,now,max){const bucket=Math.floor(now/60000);const row=await db.prepare('INSERT INTO request_limits(key,count,expires) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1 RETURNING count').bind(key+':'+bucket,now+120000).first();if(row.count>max)fail(429,'Too many requests. Please wait one minute.');}
async function cachedPrices(db,now){const {results}=await db.prepare('SELECT * FROM live_prices').all();const values={USDC:{price:SCALE,at:now}};for(const r of results)if(ASSETS.includes(r.asset))values[r.asset]={price:units(r.price),at:r.observed};return values;}
export async function priceBook(db,now,fetcher=fetch){
 let prices=await cachedPrices(db,now);
 if(Object.keys(TOKENS).every(a=>prices[a]&&now-prices[a].at<30000))return prices;
 const lease=await db.prepare("INSERT INTO refresh_leases(key,expires) VALUES('prices',?) ON CONFLICT(key) DO UPDATE SET expires=excluded.expires WHERE refresh_leases.expires<?").bind(now+12000,now).run();
 if(!lease.meta.changes)return prices;
 await Promise.all(Object.entries(TOKENS).map(async([asset,token])=>{
  try {
   const response=await fetcher('https://api.geckoterminal.com/api/v2/networks/base/tokens/'+token+'/pools?page=1',{headers:{Accept:'application/json'},signal:AbortSignal.timeout(8000)});
   if(!response.ok)throw Error('Price source unavailable');
   const body=await response.json();let best=null;
   for(const pool of body.data||[]){const b=pool.relationships?.base_token?.data?.id?.toLowerCase(),q=pool.relationships?.quote_token?.data?.id?.toLowerCase();if(![b,q].includes(USDC)||![b,q].includes('base_'+token))continue;const attr=pool.attributes||{};const value=b==='base_'+token?attr.base_token_price_usd:attr.quote_token_price_usd;const px=units(typeof value==='string'?value:'0');const liquidity=Number(attr.reserve_in_usd);if(px>0n&&Number.isFinite(liquidity)&&(!best||liquidity>best.liquidity))best={px,liquidity};}
   if(!best)throw Error('NO_VALID_POOL');
   if(best)await db.prepare('INSERT INTO live_prices(asset,price,observed) VALUES(?,?,?) ON CONFLICT(asset) DO UPDATE SET price=excluded.price,observed=excluded.observed').bind(asset,fmt(best.px),now).run();
   await db.prepare('INSERT INTO feed_status(asset,success_at,successes,failures) VALUES(?,?,1,0) ON CONFLICT(asset) DO UPDATE SET success_at=excluded.success_at,successes=successes+1').bind(asset,now).run();
  }catch(error){
   console.warn(JSON.stringify({event:'price_feed_failed',asset,category:'UPSTREAM_UNAVAILABLE'}));
   await db.prepare('INSERT INTO feed_status(asset,error_at,error_code,successes,failures) VALUES(?,?,?,0,1) ON CONFLICT(asset) DO UPDATE SET error_at=excluded.error_at,error_code=excluded.error_code,failures=failures+1').bind(asset,now,'UPSTREAM_UNAVAILABLE').run();
  }
 }));
 return cachedPrices(db,now);
}
function fresh(prices,asset,now){return !!prices[asset]&&now-prices[asset].at<=120000;}
async function portfolio(db,address,prices,now){
 const account=await db.prepare('SELECT * FROM accounts WHERE address=?').bind(address).first();
 if(!account)fail(401,'Please sign in again.');
 const balances=JSON.parse(account.balances);let total=0n,priced=true;
 const items=[];
 for(const asset of ASSETS){const amount=units(balances[asset]);if(!amount&&asset!=='USDC')continue;const valid=fresh(prices,asset,now);const value=valid?amount*prices[asset].price/SCALE:null;if(value===null)priced=false;else total+=value;items.push({asset,amount:fmt(amount),price_usd:valid?fmt(prices[asset].price):null,value_usd:value===null?null:Number(fmt(value)).toFixed(2)});}
 return {balances:items,prices:Object.fromEntries(ASSETS.map(a=>[a,fresh(prices,a,now)?fmt(prices[a].price):null])),total_usd:priced?Number(fmt(total)).toFixed(2):null,start_usd:'100',prices_fresh:priced};
}
async function signedIn(request,db,now){const cookie=request.headers.get('Cookie')||'';const token=cookie.match(/(?:^|;\s*)cimp_session=([a-f0-9]{64})(?:;|$)/)?.[1];if(!token)fail(401,'Not signed in.');const session=await db.prepare('SELECT address FROM sessions WHERE hash=? AND expires>?').bind(await hash(token),now).first();if(!session)fail(401,'Session expired. Please sign in again.');await db.prepare('UPDATE accounts SET last_seen=? WHERE address=? AND last_seen<?').bind(now,session.address,now-300000).run();return session.address;}
const user=address=>({address,display_name:null,role:'member'});
async function body(request){if(Number(request.headers.get('content-length')||0)>4096)fail(413,'Request is too large.');const reader=request.body?.getReader();const chunks=[];let size=0;if(reader){for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>4096){await reader.cancel();fail(413,'Request is too large.');}chunks.push(value);}}const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}try{const value=JSON.parse(new TextDecoder().decode(bytes));if(!value||typeof value!=='object'||Array.isArray(value))fail(400,'JSON must be an object.');return value;}catch{fail(400,'JSON must be an object.');}}
async function dispatch(request,db,{origin,now,fetcher,clock}){
 const url=new URL(request.url),path=url.pathname.replace(/\/$/,'');
 const write=['POST','PUT','PATCH','DELETE'].includes(request.method);
 if(write){if(request.method!=='POST')fail(405,'Method not allowed.');if((request.headers.get('content-type')||'').split(';')[0].trim().toLowerCase()!=='application/json')fail(415,'Content-Type must be application/json.');const suppliedOrigin=request.headers.get('origin');if(suppliedOrigin&&suppliedOrigin!==origin)fail(403,'Cross-origin writes are blocked.');if(request.headers.get('sec-fetch-site')==='cross-site')fail(403,'Cross-site writes are blocked.');}
 if(!write&&request.method!=='GET')fail(405,'Method not allowed.');
 const ip=await hash(request.headers.get('cf-connecting-ip')||'unknown');
 if(path==='/api/release'&&!write)return json({...RELEASE,features:FEATURES});
 if(path==='/api/health'&&!write){await db.prepare('SELECT 1').first();const prices=await cachedPrices(db,now);return json({ok:true,mode:'paper-only',backend:'cloudflare-d1',prices_fresh:Object.keys(TOKENS).every(a=>fresh(prices,a,now)),features:FEATURES,release:RELEASE});}
 if(path==='/api/ready'&&!write){const prices=await priceBook(db,now,fetcher);const ready=Object.keys(TOKENS).every(a=>fresh(prices,a,now));const {results}=await db.prepare('SELECT * FROM feed_status').all();return json({ok:ready,status:ready?'ready':'degraded',database:'reachable',release:RELEASE,features:FEATURES,feed:results.map(r=>({asset:r.asset,age_s:prices[r.asset]?Math.max(0,Math.floor((now-prices[r.asset].at)/1000)):null,last_success_at:r.success_at,last_failure_at:r.error_at,last_error:r.error_code,successes:r.successes,failures:r.failures}))},ready?200:503);}
 if(path==='/api/bot')return json({available:false,mode:'paper-only',detail:'Scheduled paper bots are not supported on this hosted release. Manual paper trading remains available.'},501);
 if(path==='/api/auth/nonce'&&!write){
  await rate(db,'nonce:'+ip,now,20);
  let address;try{address=getAddress(url.searchParams.get('address')||'');}catch{fail(400,'Invalid wallet address.');}
  const chain=Number(url.searchParams.get('chain_id')||84532);
  if(![1,8453,84532,11155111].includes(chain))fail(400,'Use Ethereum, Base, Base Sepolia or Ethereum Sepolia for wallet sign-in.');
  const nonce=random(),expires=now+600000;
  const message=`${new URL(origin).host} wants you to sign in with your Ethereum account:\n${address}\n\nSign in to Cimphawng paper trading. Free message signature only. No transaction or token approval.\n\nURI: ${origin}\nVersion: 1\nChain ID: ${chain}\nNonce: ${nonce}\nIssued At: ${new Date(now).toISOString()}\nExpiration Time: ${new Date(expires).toISOString()}`;
  await db.batch([db.prepare('DELETE FROM auth_nonces WHERE expires<?').bind(now),db.prepare('DELETE FROM sessions WHERE expires<?').bind(now),db.prepare('DELETE FROM request_limits WHERE expires<?').bind(now),db.prepare('DELETE FROM api_metrics WHERE minute<?').bind(Math.floor(now/60000)-60),db.prepare('INSERT INTO auth_nonces(nonce,address,message,expires,used) VALUES(?,?,?,?,0)').bind(nonce,address.toLowerCase(),message,expires)]);
  return json({nonce,message});
 }
 if(path==='/api/auth/verify'&&write){
  await rate(db,'verify:'+ip,now,40);const input=await body(request);
  if(typeof input.nonce!=='string'||!/^([a-f0-9]{64})$/.test(input.nonce)||typeof input.signature!=='string'||input.signature.length>200)fail(400,'Invalid sign-in request.');
  // UPDATE RETURNING atomically consumes the nonce before any signature verification.
  const row=await db.prepare('UPDATE auth_nonces SET used=1 WHERE nonce=? AND used=0 AND expires>? RETURNING address,message').bind(input.nonce,now).first();
  if(!row)fail(401,'Sign-in request expired or already used.');
  let signer;try{signer=verifyMessage(row.message,input.signature).toLowerCase();}catch{fail(401,'Invalid signature.');}if(signer!==row.address)fail(401,'Signature does not match the wallet.');
  const token=random();await db.batch([db.prepare('INSERT INTO accounts(address,balances,version,last_op,created_at,last_seen) VALUES(?,?,0,?,?,?) ON CONFLICT(address) DO UPDATE SET last_seen=excluded.last_seen').bind(signer,JSON.stringify(initial()),'',now,now),db.prepare('INSERT INTO sessions(hash,address,expires,created_at) VALUES(?,?,?,?)').bind(await hash(token),signer,now+30*86400000,now)]);
  return json(user(signer),200,{'Set-Cookie':`cimp_session=${token}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax`});
 }
 if(path==='/api/auth/logout'&&write){const cookie=request.headers.get('cookie')||'';const token=cookie.match(/(?:^|;\s*)cimp_session=([a-f0-9]{64})(?:;|$)/)?.[1];if(token)await db.prepare('DELETE FROM sessions WHERE hash=?').bind(await hash(token)).run();return json({ok:true},200,{'Set-Cookie':'cimp_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'});}
 if(path==='/api/stats'&&!write){
  const start=Date.now();const count=await db.prepare('SELECT count(*) AS members,coalesce(sum(last_seen>?),0) AS active_24h FROM accounts').bind(now-86400000).first();
  const trades=await db.prepare('SELECT count(*) AS paper_trades_total,coalesce(sum(created_at>=?),0) AS paper_trades_today FROM paper_trades').bind(Math.floor(now/86400000)*86400000).first();const ping=Date.now()-start;
  const prices=await cachedPrices(db,now);const {results}=await db.prepare('SELECT minute,status,count,duration FROM api_metrics WHERE minute>=?').bind(Math.floor(now/60000)-29).all();
  const by={'2xx':0,'3xx':0,'4xx':0,'5xx':0};for(const r of results)by[Math.min(5,Math.max(2,Math.floor(r.status/100)))+'xx']+=r.count;
  const series=Array.from({length:30},(_,i)=>{const minute=Math.floor(now/60000)-29+i;const rows=results.filter(r=>r.minute===minute);const requests=rows.reduce((s,r)=>s+r.count,0);return {requests,errors:rows.filter(r=>r.status>=500).reduce((s,r)=>s+r.count,0),avg_ms:requests?rows.reduce((s,r)=>s+r.duration,0)/requests:null};});
  return json({server:{uptime_s:null,runtime:'Cloudflare Workers',python:null,memory_peak_mb:null,load_avg:[null,null,null],cpus:null},api:{requests_total:Object.values(by).reduce((a,b)=>a+b,0),by_status:by,per_minute:series},db:{ok:true,engine:'Cloudflare D1',ping_ms:ping,size_mb:null},community:{...count,...trades},prices:{fresh:Object.keys(TOKENS).every(a=>fresh(prices,a,now)),max_age_s:120,assets:Object.fromEntries(Object.entries(prices).filter(([a])=>a!=='USDC').map(([a,p])=>[a,{price_usd:fmt(p.price),age_s:Math.max(0,Math.floor((now-p.at)/1000))}])),refresh_ok:null,refresh_failed:null,last_error:null}});
 }
 if(!['/api/me','/api/paper','/api/paper/trades','/api/paper/swap','/api/paper/reset','/api/account/export','/api/account/delete','/api/account/logout-all'].includes(path))fail(404,'Not found.');
 const address=await signedIn(request,db,now);
 if(path==='/api/me'&&!write)return json(user(address));
 if(path==='/api/account/export'&&!write){
  await rate(db,'export:'+address,now,30);
  const cursor=url.searchParams.get('cursor');let before=Number.MAX_SAFE_INTEGER,beforeId='~';
  if(cursor){const match=cursor.match(/^(\d{1,16}):([0-9a-f-]{36})$/);if(!match)fail(400,'Invalid export cursor.');before=Number(match[1]);beforeId=match[2];}
  const account=await db.prepare('SELECT address,balances,created_at,last_seen FROM accounts WHERE address=?').bind(address).first();
  const {results}=await db.prepare('SELECT id,data,created_at,archived FROM paper_trades WHERE address=? AND (created_at<? OR (created_at=? AND id<?)) ORDER BY created_at DESC,id DESC LIMIT 201').bind(address,before,before,beforeId).all();
  const rows=results.slice(0,200),last=rows.at(-1);
  return json({format_version:1,exported_at:new Date(now).toISOString(),account:{address:account.address,balances:JSON.parse(account.balances),created_at:account.created_at,last_seen:account.last_seen},trades:rows.map(r=>({...JSON.parse(r.data),archived:!!r.archived})),next_cursor:results.length>200?last.created_at+':'+last.id:null});
 }
 if(['/api/account/delete','/api/account/logout-all'].includes(path)&&write){
  const input=await body(request),token=(request.headers.get('cookie')||'').match(/(?:^|;\s*)cimp_session=([a-f0-9]{64})(?:;|$)/)?.[1];
  const session=await db.prepare('SELECT created_at FROM sessions WHERE hash=? AND address=?').bind(await hash(token||''),address).first();
  if(!session?.created_at||now-session.created_at>600000)fail(403,'Please sign out and sign in again before this account action.');
  if(path==='/api/account/logout-all'){await db.prepare('DELETE FROM sessions WHERE address=?').bind(address).run();return json({ok:true},200,{'Set-Cookie':'cimp_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'});}
  if(typeof input.confirmation!=='string'||input.confirmation.toLowerCase()!==address)fail(400,'Type the connected wallet address to confirm account deletion.');
  await db.batch([db.prepare('DELETE FROM operation_receipts WHERE address=?').bind(address),db.prepare('DELETE FROM paper_trades WHERE address=?').bind(address),db.prepare('DELETE FROM sessions WHERE address=?').bind(address),db.prepare('DELETE FROM auth_nonces WHERE address=?').bind(address),db.prepare('DELETE FROM request_limits WHERE key LIKE ? OR key LIKE ?').bind('paper:'+address+':%','export:'+address+':%'),db.prepare('DELETE FROM accounts WHERE address=?').bind(address)]);
  return json({ok:true,deleted:'wallet paper account',note:'This does not alter blockchain transactions or tokens. Provider backups may retain historical copies for their retention period.'},200,{'Set-Cookie':'cimp_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'});
 }

 if(path==='/api/paper/trades'&&!write){const limit=Number(url.searchParams.get('limit')||50);if(!Number.isInteger(limit)||limit<1||limit>200)fail(400,'Limit must be between 1 and 200.');const {results}=await db.prepare('SELECT data FROM paper_trades WHERE address=? AND archived=0 ORDER BY created_at DESC,id DESC LIMIT ?').bind(address,limit).all();return json({trades:results.map(r=>JSON.parse(r.data))});}
 if(path==='/api/paper'&&!write)return json(await portfolio(db,address,await priceBook(db,now,fetcher),now));
 if(!write||!['/api/paper/swap','/api/paper/reset'].includes(path))fail(405,'Method not allowed.');
 const input=await body(request),kind=path.endsWith('/reset')?'reset':'swap';
 const key=request.headers.get('Idempotency-Key');
 if(!key||!/^[-a-zA-Z0-9_]{16,80}$/.test(key))fail(400,'A unique Idempotency-Key is required for each paper operation.');
 const payloadHash=await hash(JSON.stringify(kind==='swap'?[kind,input.from_asset,input.to_asset,input.amount]:[kind]));
 async function replay(){const receipt=await db.prepare('SELECT kind,payload_hash,result FROM operation_receipts WHERE address=? AND key=?').bind(address,key).first();if(!receipt)return null;if(receipt.kind!==kind||receipt.payload_hash!==payloadHash)fail(409,'That request ID was already used for a different operation.');const stored=JSON.parse(receipt.result),pf=await portfolio(db,address,await cachedPrices(db,now),now);return json(kind==='swap'?{trade:stored.trade,portfolio:pf,replayed:true}:{...pf,replayed:true});}
 const previous=await replay();if(previous)return previous;
 await rate(db,'paper:'+address,now,60);
 const account=await db.prepare('SELECT * FROM accounts WHERE address=?').bind(address).first();if(!account)fail(401,'Account no longer exists.');const op=crypto.randomUUID();
 async function commit(statements){try{return await db.batch(statements);}catch(error){const prior=await replay();if(prior)return prior;throw error;}}
 const receipt=result=>db.prepare('INSERT INTO operation_receipts(address,key,kind,payload_hash,result,created_at) SELECT ?,?,?,?,?,? WHERE EXISTS(SELECT 1 FROM accounts WHERE address=? AND last_op=?)').bind(address,key,kind,payloadHash,JSON.stringify(result),now,address,op);
 if(kind==='reset'){
  const result=await commit([db.prepare('UPDATE accounts SET balances=?,version=version+1,last_op=? WHERE address=? AND version=?').bind(JSON.stringify(initial()),op,address,account.version),db.prepare('UPDATE paper_trades SET archived=1 WHERE address=? AND EXISTS(SELECT 1 FROM accounts WHERE address=? AND last_op=?)').bind(address,address,op),receipt({reset:true})]);
  if(result instanceof Response)return result;
 if(!result[0].meta.changes){const prior=await replay();if(prior)return prior;fail(409,'Portfolio changed. Refresh and retry with the same request ID.');}return json(await portfolio(db,address,await cachedPrices(db,now),now));
 }
 const from=input.from_asset,to=input.to_asset;if(!ASSETS.includes(from)||!ASSETS.includes(to)||from===to)fail(400,'Pick two different supported assets.');const amount=units(input.amount);if(amount<=0n)fail(400,'Amount must be positive.');
 const prices=await priceBook(db,now,fetcher);const checkedAt=clock();
 if(!fresh(prices,from,checkedAt)||!fresh(prices,to,checkedAt))fail(503,'Live prices are unavailable or stale. No paper trade was placed.');
 const balances=JSON.parse(account.balances);if(units(balances[from])<amount)fail(400,'Not enough '+from+'.');
 const usd=amount*prices[from].price/SCALE;if(usd<SCALE/100n)fail(400,'Minimum paper trade is $0.01.');const fee=usd*3n/1000n;const out=(usd-fee)*SCALE/prices[to].price;if(out<=0n)fail(400,'Trade amount is too small.');
 balances[from]=fmt(units(balances[from])-amount);balances[to]=fmt(units(balances[to])+out);
 const trade={id:op,from_asset:from,to_asset:to,amount_in:fmt(amount),amount_out:fmt(out),price_in_usd:fmt(prices[from].price),price_out_usd:fmt(prices[to].price),fee_usd:fmt(fee),created_at:new Date(now).toISOString()};
 const result=await commit([db.prepare('UPDATE accounts SET balances=?,version=version+1,last_op=? WHERE address=? AND version=?').bind(JSON.stringify(balances),op,address,account.version),db.prepare('INSERT INTO paper_trades(id,address,data,created_at,archived) SELECT ?,?,?,?,0 WHERE EXISTS(SELECT 1 FROM accounts WHERE address=? AND last_op=?)').bind(op,address,JSON.stringify(trade),now,address,op),receipt({trade})]);
 if(result instanceof Response)return result;
 if(!result[0].meta.changes){const prior=await replay();if(prior)return prior;fail(409,'Portfolio changed. Refresh and retry with the same request ID.');}
 return json({trade,portfolio:await portfolio(db,address,prices,now)});
}
export async function handleApi(request,db,options={}){
 const start=Date.now(),requestId=crypto.randomUUID();const context={origin:SITE_ORIGIN,fetcher:fetch,clock:Date.now,...options};context.now=context.clock();let response;
 try{
  if(!db)fail(503,'Database is not configured.');
  const pathname=new URL(request.url).pathname;
  if(!['/api/health','/api/release'].includes(pathname))await rate(db,'api:'+await hash(request.headers.get('cf-connecting-ip')||'unknown'),context.now,180);
  response=await dispatch(request,db,context);
 }catch(error){
  if(!error.status)console.error(JSON.stringify({event:'api_error',request_id:requestId,path:new URL(request.url).pathname,status:503,category:error.name||'Error'}));
  response=json({detail:error.status?error.message:'The service is temporarily unavailable.',request_id:requestId},error.status||503);
 }
 response.headers.set('X-Request-Id',requestId);
 if(response.status===429)response.headers.set('Retry-After','60');
 if(db)try{await db.prepare('INSERT INTO api_metrics(minute,status,count,duration) VALUES(?,?,1,?) ON CONFLICT(minute,status) DO UPDATE SET count=count+1,duration=duration+excluded.duration').bind(Math.floor(context.now/60000),response.status,Date.now()-start).run();}catch{console.error(JSON.stringify({event:'metrics_write_failed',request_id:requestId}));}
 return response;
}
