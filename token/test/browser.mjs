import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import ganache from 'ganache';
const root = fileURLToPath(new URL('../../',import.meta.url));
const raw = ganache.provider({chain:{chainId:84532},logging:{quiet:true}});
const accounts = await raw.request({method:'eth_accounts',params:[]});
const server = http.createServer(async(req,res)=>{
  try {
    let name = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if (name.endsWith('/')) name += 'index.html';
    const file=path.resolve(root,'.'+name);
    if (!file.startsWith(root)) {res.writeHead(403).end();return;}
    const types={'.html':'text/html','.js':'text/javascript','.json':'application/json','.md':'text/plain'};
    res.setHeader('Content-Type',types[path.extname(file)]||'text/plain');res.end(await fs.readFile(file));
  } catch {res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true, executablePath:process.env.CIMP_CHROME_EXECUTABLE || undefined, args:['--no-sandbox']});
const base=`http://127.0.0.1:${server.address().port}`;
const errors=[];
try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  page.on('pageerror',err=>errors.push(err.message));
  await page.goto(base+'/token/');
  await page.click('#language');
  await page.click('#connect');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('wallet extension'));
  assert.equal(await page.locator('#deploy').isDisabled(),true);
  await page.exposeFunction('testRpc',async({method,params})=> raw.request({method:method==='eth_requestAccounts'?'eth_accounts':method,params:params||[]}));
  await page.addInitScript(()=>{
    const handlers={};
    window.ethereum={
      wrong:false,
      request(args){if(args.method==='eth_chainId'&&this.wrong)return Promise.resolve('0x2105');return window.testRpc(args);},
      on(event,fn){(handlers[event]??=[]).push(fn);},
      removeListener(event,fn){handlers[event]=(handlers[event]||[]).filter(x=>x!==fn);},
      emit(event,value){for(const fn of handlers[event]||[])fn(value);}
    };
  });
  await page.reload();
  await page.click('#connect');
  await page.waitForFunction(()=>document.querySelector('#account').textContent.startsWith('0x'));
  await page.check('#ack');
  await page.waitForFunction(()=>!document.querySelector('#deploy').disabled);
  await page.click('#deploy');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('deployed and verified'),{},{timeout:20000});
  const address=await page.locator('#contract a').textContent();
  assert.match(address,/^0x[0-9A-Fa-f]{40}$/);
  assert.equal(await page.locator('#balance').textContent(),'1000000.0 CIMP');
  await page.fill('#recipient',accounts[1]);await page.fill('#amount','12.5');await page.click('#transfer');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('transfer confirmed'),{},{timeout:20000});
  assert.equal(await page.locator('#balance').textContent(),'999987.5 CIMP');
  await page.fill('#amount','9999999');await page.click('#transfer');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Insufficient'));
  await page.fill('#address',accounts[1]);await page.click('#attach');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('does not match'));
  // A failed attachment must not change the previously verified contract.
  assert.equal(await page.locator('#contract a').textContent(),address);
  await page.evaluate(()=>{window.ethereum.wrong=true;window.ethereum.emit('chainChanged','0x2105');});
  assert.equal(await page.locator('#transfer').isDisabled(),true);
  await page.click('#connect');
  await page.waitForFunction(()=>!document.querySelector('#switch').hidden);
  assert.equal(await page.locator('#deploy').isDisabled(),true);
  assert.equal(await page.locator('#attach').isDisabled(),true);
  await page.evaluate(()=>{window.ethereum.wrong=false;window.ethereum.emit('chainChanged','0x14a34');});
  await page.click('#connect');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Previously selected'));
  assert.equal(await page.locator('#balance').textContent(),'999987.5 CIMP');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'/tmp/cimp-testnet-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.goto(base+'/index.html');
  assert.equal(await page.locator('a[href="./token/"]').count(),1);
  assert.deepEqual(errors,[]);
  console.log('Browser checks passed: no-wallet state, deployment, exact-bytecode loading, balance, transfer, insufficient funds, mismatched contract, wrong network, reconnect, persisted selection, mobile/desktop layout, terminal link.');
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));await raw.disconnect();}
