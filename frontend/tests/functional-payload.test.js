import test from 'node:test';
import assert from 'node:assert/strict';
import { functionalPayload, responseError } from '../src/utils/FunctionalPayload.js';

test('functional-only design keeps species and all interaction participants', () => {
  const species = [{ name: 'RNA', type: 'RNA', uri: '' }];
  const interactions = [{ type: 'Genetic Production', participants: {
    Product: [{ name: 'RNA' }], Template: [{ name: 'CDS', instance_id: 2 }],
  } }];
  const original = structuredClone({ interactions, species });
  const payload = functionalPayload([], interactions, species);
  assert.deepEqual(payload.interactions[0].participants, { Product: ['RNA'], Template: ['CDS_2'] });
  assert.deepEqual(payload.eds, species);
  assert.deepEqual({ interactions, species }, original);
});

test('operon references preserve repeated DNA part instances', () => {
  const parts = [{ name: 'RBS', instance_id: 1 }, { name: 'RBS', instance_id: 2 }];
  const payload = functionalPayload([{ name: 'op', components: parts, unions: [
    { from: parts[0], to: parts[1], type: 'Order' },
  ] }], [], []);
  assert.deepEqual(payload.expressions[0].components, ['RBS_1', 'RBS_2']);
  assert.deepEqual(payload.expressions[0].unions[0], { from: 'RBS_1', to: 'RBS_2', type: 'Order' });
});

test('validation errors include actionable paths and messages', async () => {
  const message = await responseError({ json: async () => ({ error: 'Invalid design', issues: [
    { path: 'interactions[0].participants.Stimulator', message: 'Incompatible with Inhibition' },
  ] }) });
  assert.match(message, /interactions\[0\].participants.Stimulator: Incompatible/);
});

test('non-JSON error response has a retry message', async () => {
  const message = await responseError({ json: async () => { throw Error('HTML'); } });
  assert.match(message, /design has been kept/);
});
