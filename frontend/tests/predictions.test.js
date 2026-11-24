import test from 'node:test';
import assert from 'node:assert/strict';
import { GLYPH_TO_ROLE, updatePredictions } from '../src/utils/PredictionUtils.js';

test('all fourteen foreground mappings are explicit, including cds-arrow', () => {
  assert.equal(Object.keys(GLYPH_TO_ROLE).length, 14);
  for (const [glyph, role] of Object.entries(GLYPH_TO_ROLE)) {
    const rows = updatePredictions({ pred_classes: [glyph], draw_boxes: [[0, 0, 1, 1]] }, {});
    assert.equal(rows[1].role, role);
  }
});

test('background is excluded and unknown classes fail actionably before replacement', () => {
  assert.equal(updatePredictions({ pred_classes: ['__background__'], draw_boxes: [[0, 0, 1, 1]] }, {}).length, 1);
  assert.throws(() => updatePredictions({ pred_classes: ['future'], draw_boxes: [[0, 0, 1, 1]] }, {}), /Unknown detector class.*draft was kept/);
});

for (const glyph of ['constructor', '__proto__', null, 42]) {
  test(`unrecognized class ${glyph} cannot inherit a role`, () => {
    assert.throws(() => updatePredictions({ pred_classes: [glyph], draw_boxes: [[0, 0, 1, 1]] }, {}), /draft was kept/);
  });
}
