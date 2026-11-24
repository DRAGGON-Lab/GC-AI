/** Return fresh rows and recompute duplicate instance numbers without mutation. */
export function numberInstances(rows) {
  return rows.map(row => {
    const copy = { ...row };
    delete copy.instance_id;
    const peers = rows.filter(other => other.name && other.name === row.name && other.role === row.role);
    if (peers.length > 1) copy.instance_id = peers.findIndex(other => other.id === row.id) + 1;
    return copy;
  });
}

export function patchPart(rows, identity, patch) {
  return numberInstances(rows.map(row => row.id === identity ? { ...row, ...patch } : row));
}
