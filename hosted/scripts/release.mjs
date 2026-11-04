import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root=process.cwd(),repo=fs.existsSync(path.join(root,'hosted/lib/hosted-api.mjs')),prefix=repo?'hosted/':'';
const files=['lib/hosted-api.mjs','db/schema.ts',...fs.readdirSync(prefix+'drizzle').filter(n=>n.endsWith('.sql')).sort().map(n=>'drizzle/'+n)];
const assets=['index.html','ui.css','desk.html','token/index.html','token/app.js','guide.html','account.html','status.html','account.js','status.js','beta.css'];
const hash=crypto.createHash('sha256');
for(const name of files)hash.update(name+'\0').update(fs.readFileSync(prefix+name));
for(const name of assets)hash.update(name+'\0').update(fs.readFileSync((repo?'':'public/')+name));
const release={version:'0.2.0-beta.1',fingerprint:hash.digest('hex'),source_base:'8fbadbcf73c7024ad4449cec69b542bf093745ef',channel:'private-beta'};
const generated='export default '+JSON.stringify(release)+';\n';
if(process.argv.includes('--check')){if(fs.readFileSync(prefix+'lib/release.mjs','utf8')!==generated)throw Error('Release fingerprint mismatch. Run the release script after modifying release inputs.');console.log('Release fingerprint matches '+release.fingerprint);}
else {fs.writeFileSync(prefix+'lib/release.mjs',generated);console.log('Generated release '+release.fingerprint);}
