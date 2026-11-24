import test from 'node:test';
import assert from 'node:assert/strict';
import { numberInstances, patchPart } from '../src/utils/Draft.js';

test('editing and removing duplicate parts never mutates previous draft snapshots', () => {
  const previous = Object.freeze([
    Object.freeze({ id: 'a', name: 'X', role: 'CDS' }),
    Object.freeze({ id: 'b', name: 'X', role: 'CDS' }),
  ]);
  const numbered = numberInstances(previous);
  assert.deepEqual(numbered.map(row => row.instance_id), [1, 2]);
  const renamed = patchPart(numbered, 'a', { name: 'Y' });
  assert.deepEqual(renamed.map(row => row.instance_id), [undefined, undefined]);
  assert.equal(numbered[0].name, 'X');
  assert.equal(numbered[0].instance_id, 1);
  assert.equal(previous[0].instance_id, undefined);
});
