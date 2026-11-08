import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {assets,releaseFor,releaseInputs,releaseModule,repoRoot} from './release.mjs';

const [checkout,expectedCommit]=process.argv.slice(2);
if(!checkout||!path.isAbsolute(checkout)||!(/^[0-9a-f]{40}$/.test(expectedCommit??''))){
 throw Error('Usage: node hosted/scripts/stage-site.mjs /absolute/site/checkout <reviewed-github-sha>');
}
const git=(cwd,...args)=>execFileSync('git',args,{cwd,encoding:'utf8'}).trim();
const site=fs.realpathSync(checkout);
if(git(repoRoot,'rev-parse','HEAD')!==expectedCommit||git(repoRoot,'status','--porcelain'))throw Error('Open a clean checkout at the reviewed GitHub commit.');
if(fs.realpathSync(git(site,'rev-parse','--show-toplevel'))!==site||git(site,'status','--porcelain'))throw Error('Open a clean Site source checkout.');
if(!JSON.parse(fs.readFileSync(path.join(site,'.openai/hosting.json'),'utf8')).project_id||
 !fs.existsSync(path.join(site,'app/route.ts')))throw Error('Expected an existing Cimphawng Site checkout.');

const release=releaseFor(repoRoot,true);
const module=fs.readFileSync(path.join(repoRoot,'hosted/lib/release.mjs'),'utf8');
if(module!==releaseModule(release))throw Error('The reviewed GitHub fingerprint is invalid.');
const tracked=new Set(git(repoRoot,'ls-files').split('\n'));
const inputs=releaseInputs(repoRoot,true);
for(const {source} of inputs)if(!tracked.has(source))throw Error('Untracked release input: '+source);
const unexpected=git(site,'ls-files','public').split('\n').filter(name=>name&&name!=='public/release-provenance.json'&&!assets.includes(name.slice(7)));
if(unexpected.length)throw Error('Review Site-only public assets before staging: '+unexpected.join(', '));
for(const {source,target} of inputs){
 const dst=path.join(site,target);
 fs.mkdirSync(path.dirname(dst),{recursive:true});
 fs.copyFileSync(path.join(repoRoot,source),dst);
}
fs.writeFileSync(path.join(site,'lib/release.mjs'),module);
fs.copyFileSync(path.join(site,'public/index.html'),path.join(site,'site/terminal.html'));
if(releaseFor(site,false).fingerprint!==release.fingerprint)throw Error('Staged Site fingerprint differs from GitHub.');
fs.writeFileSync(path.join(site,'public/release-provenance.json'),JSON.stringify({
 github_commit:expectedCommit,fingerprint:release.fingerprint,channel:release.channel
})+'\n');
console.log('Staged GitHub '+expectedCommit+' with fingerprint '+release.fingerprint);
