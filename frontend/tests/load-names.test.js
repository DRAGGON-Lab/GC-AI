import test from 'node:test';
import assert from 'node:assert/strict';
import { loadNames } from '../src/utils/LoadNames.js';

const roles = Array.from({ length: 14 }, (_, index) => `role_${index}`);
const response = (status, names = [], retryAfter = null) => ({
  ok: status === 200,
  status,
  headers: { get: () => retryAfter },
  json: async () => names,
});
const roleFrom = url => new URL(url, 'https://gcai.test').searchParams.get('role');
const noWait = async () => {};

function cappedFetch(capacity = 4) {
  let active = 0;
  let peak = 0;
  const calls = [];
  return {
    calls,
    get peak() { return peak; },
    fetch: async url => {
      calls.push(roleFrom(url));
      active += 1;
      peak = Math.max(peak, active);
      const overloaded = active > capacity;
      await new Promise(resolve => setTimeout(resolve, 2));
      active -= 1;
      return overloaded ? response(503) : response(200, [`part_for_${roleFrom(url)}`]);
    },
  };
}

test('parallel registry loading exceeds proxy capacity; helper completes all fourteen at concurrency two', async () => {
  const previous = cappedFetch();
  await assert.rejects(Promise.all(roles.map(async role => {
    const result = await previous.fetch(`/api/component/names?role=${role}`);
    if (!result.ok) throw new Error('503: registry load failed');
    return result.json();
  })), /503/);
  assert.equal(previous.peak, 14);

  const server = cappedFetch();
  const result = await loadNames(roles, { fetchImpl: server.fetch });
  assert.equal(server.peak, 2);
  assert.equal(server.calls.length, 14);
  assert.deepEqual(result.failedRoles, []);
  assert.deepEqual(Object.keys(result.namesCache).sort(), [...roles].sort());
});

test('transient busy responses honor capped Retry-After before retrying', async () => {
  for (const [header, delay] of [['2', 2000], ['120', 5000], ['0', 0], ['invalid', 1000], [new Date(Date.now() + 60_000).toUTCString(), 5000]]) {
    const waits = [];
    let calls = 0;
    const result = await loadNames(['Promoter'], {
      fetchImpl: async () => ++calls === 1 ? response(503, [], header) : response(200, ['part']),
      wait: async milliseconds => { waits.push(milliseconds); },
    });
    assert.equal(calls, 2);
    assert.deepEqual(waits, [delay]);
    assert.deepEqual(result.namesCache, { Promoter: ['part'] });
    assert.deepEqual(result.failedRoles, []);
  }
});

test('permanent errors preserve successful roles and retry only unresolved roles', async () => {
  const calls = [];
  const first = await loadNames(['Promoter', 'CDS', 'RBS'], {
    fetchImpl: async url => {
      const role = roleFrom(url);
      calls.push(role);
      return role === 'CDS' ? response(503) : role === 'RBS' ? response(404) : response(200, ['known_part']);
    },
    wait: noWait,
  });
  assert.equal(calls.filter(role => role === 'CDS').length, 3);
  assert.equal(calls.filter(role => role === 'RBS').length, 1);
  assert.deepEqual(first.namesCache, { Promoter: ['known_part'] });
  assert.deepEqual(first.failedRoles, ['CDS', 'RBS']);
  const retryCalls = [];
  const retry = await loadNames(['Promoter', 'CDS', 'RBS'], {
    existingNames: first.namesCache,
    fetchImpl: async url => { retryCalls.push(roleFrom(url)); return response(200, ['recovered_part']); },
  });
  assert.deepEqual(retryCalls.sort(), ['CDS', 'RBS']);
  assert.deepEqual(retry.namesCache.Promoter, ['known_part']);
  assert.deepEqual(retry.failedRoles, []);
});

test('network and malformed response errors remain recoverable failures', async () => {
  for (const fetchImpl of [async () => { throw new Error('network'); }, async () => response(200, {})]) {
    const result = await loadNames(['Promoter'], { fetchImpl });
    assert.deepEqual(result.namesCache, {});
    assert.deepEqual(result.failedRoles, ['Promoter']);
  }
});

test('abort cancels in-flight requests and never starts queued roles', async () => {
  const controller = new AbortController();
  let calls = 0;
  const pending = loadNames(roles, {
    signal: controller.signal,
    fetchImpl: (url, { signal }) => {
      calls += 1;
      assert.equal(signal, controller.signal);
      return new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('Canceled', 'AbortError')), { once: true });
      });
    },
  });
  assert.equal(calls, 2);
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(calls, 2);
});

test('abort interrupts Retry-After wait without issuing another request', { timeout: 500 }, async () => {
  const controller = new AbortController();
  let calls = 0;
  const pending = loadNames(['Promoter'], {
    signal: controller.signal,
    fetchImpl: async () => { calls += 1; return response(503, [], '5'); },
  });
  const rejected = assert.rejects(pending, { name: 'AbortError' });
  await new Promise(resolve => setTimeout(resolve, 10));
  controller.abort();
  await rejected;
  assert.equal(calls, 1);
});

test('an already-aborted load never fetches or mutates previous successes', async () => {
  const controller = new AbortController();
  controller.abort();
  const existingNames = { CDS: ['known_part'] };
  await assert.rejects(loadNames(['Promoter', 'CDS'], {
    signal: controller.signal,
    existingNames,
    fetchImpl: () => assert.fail('Canceled load fetched a role'),
  }), { name: 'AbortError' });
  assert.deepEqual(existingNames, { CDS: ['known_part'] });
});
