import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import solc from 'solc';
const root = fileURLToPath(new URL('../', import.meta.url));
const input = {
  language: 'Solidity',
  sources: { 'CimphawngTestToken.sol': { content: fs.readFileSync(path.join(root, 'contracts/CimphawngTestToken.sol'), 'utf8') } },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    evmVersion: 'paris',
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object', 'evm.deployedBytecode.object', 'metadata'] } }
  }
};
const sources = { ...input.sources };
const output = JSON.parse(solc.compile(JSON.stringify(input), { import(name) {
  if (!name.startsWith('@openzeppelin/contracts/') || name.includes('..')) return { error: 'Unsupported import' };
  const content = fs.readFileSync(path.join(root, 'node_modules', name), 'utf8');
  sources[name] = { content };
  return { contents: content };
} }));
for (const error of output.errors || []) {
  if (error.severity === 'error') throw new Error(error.formattedMessage);
}
const c = output.contracts['CimphawngTestToken.sol'].CimphawngTestToken;
const artifact = { contractName: 'CimphawngTestToken', compiler: solc.version(), chainId: 84532,
  abi: c.abi, bytecode: '0x' + c.evm.bytecode.object, deployedBytecode: '0x' + c.evm.deployedBytecode.object };
fs.mkdirSync(path.join(root, 'web'), { recursive: true });
fs.writeFileSync(path.join(root, 'web/CimphawngTestToken.json'), JSON.stringify(artifact, null, 2) + '\n');
fs.writeFileSync(path.join(root, 'web/standard-input.json'), JSON.stringify({ ...input, sources }, null, 2) + '\n');
fs.copyFileSync(path.join(root, 'node_modules/ethers/dist/ethers.umd.min.js'), path.join(root, 'web/ethers.umd.min.js'));
fs.copyFileSync(path.join(root, 'node_modules/ethers/LICENSE.md'), path.join(root, 'web/ethers-LICENSE.md'));
console.log('Built CIMP artifact, explorer verification input, and local wallet library.');
