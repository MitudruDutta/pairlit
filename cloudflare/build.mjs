import {cpSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';

mkdirSync('dist/server', {recursive:true});
mkdirSync('dist/client', {recursive:true});
mkdirSync('dist/.openai', {recursive:true});
cpSync('apps/web/out', 'dist/client', {recursive:true});
cpSync('cloudflare/worker.mjs', 'dist/server/index.js');
cpSync('.openai/hosting.json', 'dist/.openai/hosting.json');
writeFileSync('dist/server/wrangler.json', JSON.stringify({
  name: 'pairlit-social', main: './index.js', compatibility_date: '2026-10-02',
  assets: {directory:'../client', binding:'ASSETS'},
}, null, 2));
const hosting = JSON.parse(readFileSync('.openai/hosting.json', 'utf8'));
if (!hosting.project_id) throw new Error('Missing Sites project ID');
console.log('Cloudflare artifact prepared; runtime origin configured through hosting environment.');
