import assert from 'node:assert/strict';
import test from 'node:test';
import {
  request,
  basePath,
  newPage,
} from '../../src/dockflow_pipelines/static/api.js';

test('API helper rejects network paths and backslash URL normalization', async () => {
  for (const path of [
    'https://external.invalid/data',
    '//external.invalid/data',
    '/\\external.invalid/data',
  ]) {
    await assert.rejects(request(path), /Only same-origin/);
  }
});

test('requests retain the mounted prefix and omit browser credentials and redirects', async (t) => {
  let captured;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    captured = { url, options };
    return new Response('{"ok":true}', { status: 200 });
  });
  assert.deepEqual(await request('/dockflow/v1/capabilities'), { ok: true });
  assert.equal(captured.url, basePath + '/dockflow/v1/capabilities');
  assert.equal(captured.options.credentials, 'omit');
  assert.equal(captured.options.redirect, 'error');
});

test('structured service errors preserve code, details and request ID', async (t) => {
  t.mock.method(
    globalThis,
    'fetch',
    async () =>
      new Response(
        JSON.stringify({
          error: {
            code: 'CONFLICT',
            message: 'Already exists',
            request_id: 'request-one',
            details: [{ field: 'name', reason: 'duplicate' }],
          },
        }),
        { status: 409 },
      ),
  );
  await assert.rejects(request('/dockflow/v1/runs'), (error) => {
    assert.equal(error.status, 409);
    assert.equal(error.code, 'CONFLICT');
    assert.equal(error.requestId, 'request-one');
    assert.deepEqual(error.details, [{ field: 'name', reason: 'duplicate' }]);
    return true;
  });
});

test('non-JSON unauthorized response still requests authentication', async (t) => {
  const previous = globalThis.window;
  const events = [];
  globalThis.window = { dispatchEvent: (event) => events.push(event.type) };
  t.after(() => {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  });
  t.mock.method(
    globalThis,
    'fetch',
    async () => new Response('<html>Unauthorized</html>', { status: 401 }),
  );
  await assert.rejects(
    request('/dockflow/v1/openapi.json'),
    (error) => error.status === 401 && error.message.includes('HTTP 401'),
  );
  assert.deepEqual(events, ['dockflow:unauthorized']);
});

test('non-JSON gateway failure is actionable and successful malformed JSON is rejected', async (t) => {
  t.mock.method(
    globalThis,
    'fetch',
    async () => new Response('Bad gateway', { status: 502 }),
  );
  await assert.rejects(
    request('/health/ready'),
    (error) => error.status === 502 && error.message.includes('HTTP 502'),
  );
  globalThis.fetch.mock.mockImplementation(
    async () => new Response('<html>Login</html>', { status: 200 }),
  );
  await assert.rejects(
    request('/dockflow/v1/runs'),
    (error) => error.code === 'INVALID_RESPONSE',
  );
});

test('navigation aborts pending requests and body-read cancellation stays an abort', async (t) => {
  let requestSignal;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requestSignal = options.signal;
    return {
      ok: true,
      status: 200,
      json: async () => {
        throw new DOMException('Cancelled', 'AbortError');
      },
    };
  });
  await assert.rejects(
    request('/dockflow/v1/runs'),
    (error) => error.name === 'AbortError',
  );
  assert.equal(requestSignal.aborted, false);
  newPage();
  assert.equal(requestSignal.aborted, true);
});
