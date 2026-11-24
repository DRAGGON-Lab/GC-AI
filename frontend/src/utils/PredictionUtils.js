export const GLYPH_TO_ROLE = Object.freeze({
      'promoter': 'Promoter',
      'terminator': 'Terminator',
      'cds': 'CDS',
      'cds-arrow': 'CDS',
      'ribosome-entry-site': 'RBS',
      'engineered-region': 'Engineered-Region',
      'operator': 'Operator',
      'primer-binding-site': 'Primer-Binding-Site',
      'origin-of-transfer': 'Origin-Of-Transfer',
      'origin-of-replication': 'Origin-Of-Replication',
      'polya': 'PolyA-Site',
      'aptamer': 'Aptamer-DNA',
      'inert-dna-spacer': 'Inert-DNA-Spacer',
      'ncrna': 'Ncrna'
});
export const updatePredictions = (predictionData, namesCache) => {
  if (!Array.isArray(predictionData.pred_classes) || !Array.isArray(predictionData.draw_boxes) ||
      predictionData.pred_classes.length !== predictionData.draw_boxes.length) {
    throw new Error('Detector classes and boxes must have matching lengths. Your draft was kept.');
  }
  if (Object.hasOwn(predictionData, 'pred_scores') &&
      (!Array.isArray(predictionData.pred_scores) || predictionData.pred_scores.length !== predictionData.pred_classes.length ||
       predictionData.pred_scores.some(score => !Number.isFinite(score) || score < 0 || score > 1))) {
    throw new Error('Model scores must match detections and be finite values within [0,1]. Your draft was kept.');
  }
  let newPredictions = predictionData.pred_classes.flatMap((role, index) => {
    if (typeof role !== 'string') throw new Error('Detector classes must be strings. Your draft was kept.');
    const box = predictionData.draw_boxes[index];
    if (!Array.isArray(box) || box.length !== 4 || box.some(value => !Number.isFinite(value)) ||
        box[2] < box[0] || box[3] < box[1]) throw new Error('Detector boxes must contain four ordered finite coordinates. Your draft was kept.');
    role = role.toLowerCase();
    if (role === '__background__') return [];
    const standardizedRole = Object.hasOwn(GLYPH_TO_ROLE, role) ? GLYPH_TO_ROLE[role] : null;
    if (!standardizedRole) throw new Error(`Unknown detector class "${role}". Your draft was kept. Check the model class configuration.`);

    return [{
      id: crypto.randomUUID(),
      uri: 'http://parts.igem.org/',
      new: false,
      identifier: '',
      name: '',
      description: '',
      role: standardizedRole,
      modelScore: predictionData.pred_scores?.[index],
      sequence: '',
      sequence_length: '',
      availableNames: namesCache[standardizedRole] || [],
      coordinates: predictionData.draw_boxes[index]
    }];
  });

  const principalComponent = {
    id: 'component-principal',
    uiIdentity: crypto.randomUUID(),
    uri: 'http://parts.igem.org/',
    new: false,
    identifier: '',
    name: '',
    description: '',
    role: '',
    availableNames: []
  };
  newPredictions.unshift(principalComponent);

  newPredictions = newPredictions.slice(1).sort((a, b) => a.coordinates[0] - b.coordinates[0]);

  newPredictions.unshift(principalComponent);

  newPredictions = newPredictions.map(prediction => {
    const rest = { ...prediction };
    delete rest.coordinates;
    return rest;
  });

  return newPredictions;
};
