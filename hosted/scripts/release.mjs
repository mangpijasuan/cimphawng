import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const localRoot=fileURLToPath(new URL('../',import.meta.url));
export const repoRoot=fs.existsSync(path.join(localRoot,'worker.mjs'))
 ? path.resolve(localRoot,'..') : null;

export const assets=[
 'account.html','account.js','assets/cimphawng-logo.jpg','beta.css','brand.css','desk.html','docs/CIMP-TESTNET.md',
 'docs/CIMP-UTILITY-PROPOSAL.md','guide.html','guided.html','guided.css','guided.mjs','guided-paper.mjs','index.html','setup.html','status.html',
 'status.js','token/app.js','token/index.html','token/web/CimphawngTestToken.json',
 'token/web/ethers-LICENSE.md','token/web/ethers.umd.min.js','token/web/standard-input.json','ui.css'
];

export function releaseInputs(root,repo){
 const backend=repo?'hosted/':'';
 const files=['lib/hosted-api.mjs','lib/ethers-server.mjs','db/schema.ts','scripts/release.mjs'];
 const migrations=path.join(root,backend,'drizzle');
 for(const name of fs.readdirSync(migrations).filter(n=>n.endsWith('.sql')).sort())files.push('drizzle/'+name);
 for(const name of fs.readdirSync(path.join(migrations,'meta')).filter(n=>n.endsWith('.json')).sort())files.push('drizzle/meta/'+name);
 return [
  ...files.map(name=>({name,source:backend+name,target:name})),
  ...assets.map(name=>({name:'public/'+name,source:(repo?'':'public/')+name,target:'public/'+name})),
 ];
}

export function releaseFor(root,repo){
 const entries=releaseInputs(root,repo).map(({name,source})=>[
  name,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,source))).digest('hex'),
 ]);
 return {
  version:'0.2.0-beta.1',fingerprint:crypto.createHash('sha256').update(JSON.stringify(entries)).digest('hex'),
  source_base:'8fbadbcf73c7024ad4449cec69b542bf093745ef',channel:'private-beta'
 };
}

export function releaseModule(release){return 'export default '+JSON.stringify(release)+';\n';}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const root=repoRoot??localRoot,release=releaseFor(root,!!repoRoot);
 const output=path.join(localRoot,'lib/release.mjs'),generated=releaseModule(release);
 if(process.argv.includes('--check')){
  if(fs.readFileSync(output,'utf8')!==generated)throw Error('Release fingerprint mismatch. Regenerate after reviewing the release inputs.');
  if(!repoRoot&&!fs.readFileSync(path.join(root,'site/terminal.html')).equals(fs.readFileSync(path.join(root,'public/index.html'))))throw Error('The served terminal differs from the fingerprinted index.');
  console.log('Release fingerprint matches '+release.fingerprint);
 }else{
  fs.writeFileSync(output,generated);
  console.log('Generated release '+release.fingerprint);
 }
}
