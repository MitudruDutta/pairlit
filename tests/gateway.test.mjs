import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker.mjs';

test('static assets receive security headers', async () => {
  const response = await worker.fetch(new Request('https://site.example/'), {ASSETS:{fetch:async()=>new Response('real static build')}});
  assert.equal(await response.text(), 'real static build');
  assert.equal(response.headers.get('X-Pairlit-Hosting'), 'cloudflare-worker');
});
test('missing origin fails explicitly; mutations require client header', async () => {
  assert.equal((await worker.fetch(new Request('https://site.example/api/state'), {})).status, 503);
  assert.equal((await worker.fetch(new Request('https://site.example/api/dates', {method:'POST'}), {})).status, 403);
});
test('proxy preserves API status and excludes browser credentials', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    assert.equal(url.href, 'https://approved-origin.example/api/state');
    assert.equal(options.headers.get('Cookie'), null);
    assert.equal(options.headers.get('Authorization'), null);
    return new Response('{"profiles":[]}', {status:200, headers:{'Content-Type':'application/json','Set-Cookie':'private=secret'}});
  };
  try {
    const response = await worker.fetch(new Request('https://site.example/api/state', {headers:{Cookie:'user=private', Authorization:'Bearer private'}}), {PAIRLIT_API_ORIGIN:'https://approved-origin.example'});
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Set-Cookie'), null);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
    assert.deepEqual(await response.json(), {profiles:[]});
  } finally { globalThis.fetch = original; }
});
