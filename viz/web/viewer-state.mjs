// Pure age/status calculations: server timestamps are monotonic and never compared to browser clocks.
export function connectionHealth(snapshot, receivedAt, now, failed = false) {
  const since = receivedAt == null ? 0 : Math.max(0, now - receivedAt) / 1000;
  const ageS = snapshot ? (snapshot.connection?.age_s ?? 0) + since : since;
  const limit = (snapshot?.config?.connection_stale_ms ?? 1000) / 1000;
  return { stale: !snapshot || failed || ageS > limit, ageS };
}

export function jointHealth(joint, connection, sinceSnapshotS, timeoutMs = 500) {
  const ageS = Math.max(0, (joint?.age_s ?? 0) + sinceSnapshotS);
  if (connection.stale) return { status: 'NO DATA', ageS, reason: 'Connection stale — readings are last received values' };
  if (!joint?.has_frame) return { status: 'NO DATA', ageS, reason: 'Waiting for first heartbeat' };
  if (ageS * 1000 > timeoutMs) return { status: 'NO DATA', ageS, reason: `No heartbeat — more than ${timeoutMs} ms since frame` };
  if (joint.dtcs?.some(d => d.rule === 'TIMEOUT')) return { status: 'NO DATA', ageS, reason: 'Heartbeat returning — waiting for healthy samples' };
  return { status: joint.status, ageS, reason: null };
}

export function nextBackoff(previous) {
  return previous === 0 ? 500 : Math.min(5000, previous * 2);
}
