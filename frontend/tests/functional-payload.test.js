import test from 'node:test';
import assert from 'node:assert/strict';
import { functionalPayload, responseError, participantOptions, selectParticipant, sameParticipantSource, ParticipantSelectionError } from '../src/utils/FunctionalPayload.js';

test('functional-only design keeps species and all interaction participants', () => {
  const species = [{ id: 'rna', name: 'RNA', type: 'RNA', uri: '' }];
  const components = [{ id: 'cds2', name: 'CDS', instance_id: 2 }];
  const options = participantOptions(components, species);
  const interactions = [{ type: 'Genetic Production', participants: {
    Product: [selectParticipant({ id: 'row1' }, options[0])],
    Template: [selectParticipant({ id: 'row2' }, options[1])],
  } }];
  const original = structuredClone({ interactions, species });
  const payload = functionalPayload([], interactions, species, components);
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

const interactionFor = row => [{ type: 'Control', participants: { Modifier: [row] } }];
const participantWire = (row, species, components) =>
  functionalPayload([], interactionFor(row), species, components).interactions[0].participants.Modifier[0];

test('same display name selects distinct DNA part and species by kind and source id', () => {
  const components = [{ id: 'part-id', name: 'LacI' }];
  const species = [{ id: 'species-id', name: 'LacI', uri: '' }];
  const options = participantOptions(components, species);
  const partOption = options.find(option => option.sourceKind === 'component');
  const speciesOption = options.find(option => option.sourceKind === 'species');
  assert.notEqual(partOption.label, speciesOption.label);
  assert.equal(sameParticipantSource(partOption, speciesOption), false);
  const part = selectParticipant({ id: 'participant-row' }, partOption);
  const protein = selectParticipant({ id: 'other-row' }, speciesOption);
  assert.equal(part.id, 'participant-row');
  assert.equal(part.sourceId, 'part-id');
  assert.equal(participantWire(part, species, components), 'LacI_1');
  assert.equal(participantWire(protein, species, components), 'LacI');
});

test('bracketed species names and URI strings are never parsed into part instances', () => {
  const components = [{ id: 'part2', name: 'X', instance_id: 2 }];
  const species = [{ id: 'species', name: 'X [2]', uri: 'https://example.org/not_a_part [9]' }];
  const option = participantOptions(components, species).find(item => item.sourceKind === 'species');
  const row = selectParticipant({ id: 'row' }, option);
  assert.equal(participantWire(row, species, components), 'X [2]');
  assert.equal(row.instance_id, '');
});

test('clearing selection keeps row identity and fails serialization without throwing in selection handler', () => {
  const option = participantOptions([{ id: 'part', name: 'X' }], [])[0];
  const selected = selectParticipant({ id: 'row' }, option);
  const cleared = selectParticipant(selected, null);
  assert.equal(cleared.id, 'row');
  assert.equal(cleared.sourceId, null);
  assert.equal(cleared.name, '');
  assert.throws(() => participantWire(cleared, [], [{ id: 'part', name: 'X' }]), ParticipantSelectionError);
});

test('removed source cannot silently bind to a same-named replacement', () => {
  const source = { id: 'original', name: 'X' };
  const row = selectParticipant({ id: 'row' }, participantOptions([source], [])[0]);
  assert.throws(() => participantWire(row, [], [{ id: 'replacement', name: 'X' }]), error =>
    error instanceof ParticipantSelectionError && error.path === 'interactions[0].participants.Modifier[0]');
});

test('current source identity resolves renamed and renumbered parts, not stale selection labels', () => {
  const option = participantOptions([{ id: 'part', name: 'X', instance_id: 2 }], [])[0];
  const row = selectParticipant({ id: 'row' }, option);
  assert.equal(participantWire(row, [], [{ id: 'part', name: 'Renamed', instance_id: 3 }]), 'Renamed_3');
  const current = participantOptions([{ id: 'part', name: 'Renamed', instance_id: 3 }], [])[0];
  assert.equal(sameParticipantSource(option, current), true);
});

test('name-only legacy participant and ambiguous duplicate source ids are rejected', () => {
  const components = [{ id: 'part', name: 'X' }];
  assert.throws(() => participantWire({ id: 'row', name: 'X' }, [], components), ParticipantSelectionError);
  const row = selectParticipant({ id: 'row' }, participantOptions(components, [])[0]);
  assert.throws(() => participantWire(row, [], [...components, { id: 'part', name: 'Y' }]), ParticipantSelectionError);
});
