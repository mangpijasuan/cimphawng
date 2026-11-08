import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './scripts/release.mjs';
const root=fileURLToPath(new URL('../',import.meta.url)),output=fileURLToPath(new URL('./public/',import.meta.url));
fs.mkdirSync(output,{recursive:true});
for(const name of assets){fs.mkdirSync(path.dirname(path.join(output,name)),{recursive:true});fs.copyFileSync(path.join(root,name),path.join(output,name));}
console.log('Prepared whitelisted static assets. Server files and secrets are excluded.');
