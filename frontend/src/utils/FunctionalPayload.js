/** Stable source identities are separate from the participant row's own id. */
export function participantOptions(components, species) {
  const parts = (components || [])
    .filter(part => part.id && part.id !== 'component-principal' && part.name)
    .map(part => ({
      sourceKind: 'component', sourceId: part.id, name: part.name,
      instance_id: part.instance_id || '',
      label: `${part.name}${part.instance_id ? ` [${part.instance_id}]` : ''} (DNA part)`,
    }));
  const functionalSpecies = (species || [])
    .filter(item => item.id && item.name)
    .map(item => ({
      sourceKind: 'species', sourceId: item.id, name: item.name, instance_id: '',
      label: `${item.name} (functional species)`,
    }));
  return [...functionalSpecies, ...parts];
}

export function sameParticipantSource(a, b) {
  return Boolean(a && b && a.sourceKind && a.sourceId
    && a.sourceKind === b.sourceKind && a.sourceId === b.sourceId);
}

/** Selecting/clearing never replaces the row id with a source's id. */
export function selectParticipant(row, option) {
  return {
    ...row,
    sourceKind: option?.sourceKind || null,
    sourceId: option?.sourceId || null,
    name: option?.name || '',
    instance_id: option?.instance_id || '',
  };
}

export class ParticipantSelectionError extends Error {
  constructor(path, message) {
    super(`${path}: ${message}`);
    this.name = 'ParticipantSelectionError';
    this.path = path;
  }
}

/** Preserve functional input and resolve each participant from its current source. */
export function functionalPayload(expressions, interactions, eds, components = []) {
  const reference = component => `${component.name}_${component.instance_id || 1}`;
  const participantReference = (member, path) => {
    if (!member || !['component', 'species'].includes(member.sourceKind) || !member.sourceId) {
      throw new ParticipantSelectionError(path, 'Select a DNA part or functional species.');
    }
    const sources = member.sourceKind === 'species' ? eds : components.filter(part => part.id !== 'component-principal');
    const matches = sources.filter(source => source.id === member.sourceId);
    if (matches.length !== 1 || !matches[0].name?.trim()) {
      throw new ParticipantSelectionError(path, 'The selected source is missing or ambiguous; select it again.');
    }
    return member.sourceKind === 'species' ? matches[0].name : reference(matches[0]);
  };
  return {
    expressions: expressions.map(expression => ({
      ...expression,
      components: expression.components.map(reference),
      unions: expression.unions.map(union => ({
        from: reference(union.from), to: reference(union.to), type: union.type,
      })),
    })),
    interactions: interactions.map((interaction, interactionIndex) => ({
      ...interaction,
      participants: Object.fromEntries(Object.entries(interaction.participants).map(([role, members]) => [
        role, members.map((member, memberIndex) => participantReference(
          member, `interactions[${interactionIndex}].participants.${role}[${memberIndex}]`,
        )),
      ])),
    })),
    eds,
  };
}

/** Read actionable API findings without treating an HTML failure as JSON. */
export async function responseError(response) {
  const fallback = 'The request failed. Your design has been kept so you can retry.';
  try {
    const body = await response.json();
    const findings = Array.isArray(body.issues) ? body.issues.map(issue =>
      `${issue.path || issue.object_id || ''}: ${issue.message || ''}`.trim()) : [];
    return [typeof body.error === 'string' ? body.error : fallback, ...findings].join('\n');
  } catch {
    return fallback;
  }
}
