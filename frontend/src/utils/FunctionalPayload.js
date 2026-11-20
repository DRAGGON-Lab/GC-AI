/** Preserve functional input regardless of whether operons were supplied. */
export function functionalPayload(expressions, interactions, eds) {
  const reference = component => `${component.name}_${component.instance_id || 1}`;
  return {
    expressions: expressions.map(expression => ({
      ...expression,
      components: expression.components.map(reference),
      unions: expression.unions.map(union => ({
        from: reference(union.from), to: reference(union.to), type: union.type,
      })),
    })),
    interactions: interactions.map(interaction => ({
      ...interaction,
      participants: Object.fromEntries(Object.entries(interaction.participants).map(([role, members]) => [
        role, members.map(member => eds.some(species => species.name === member.name)
          ? member.name : reference(member)),
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
