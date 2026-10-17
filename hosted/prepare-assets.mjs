import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),output=fileURLToPath(new URL('./public/',import.meta.url));
const files=['index.html','desk.html','ui.css','setup.html','token/index.html','token/app.js','docs/CIMP-TESTNET.md','docs/CIMP-UTILITY-PROPOSAL.md'];
fs.mkdirSync(output,{recursive:true});
for(const name of files){fs.mkdirSync(path.dirname(path.join(output,name)),{recursive:true});fs.copyFileSync(path.join(root,name),path.join(output,name));}
fs.cpSync(path.join(root,'token/web'),path.join(output,'token/web'),{recursive:true});
console.log('Prepared whitelisted static assets. Server files and secrets are excluded.');
