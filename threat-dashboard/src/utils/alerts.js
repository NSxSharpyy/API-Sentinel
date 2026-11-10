export function mergeAlerts(existing = [], incoming = []) {
  const merged = new Map();

  for (const alert of [...existing, ...incoming]) {
    if (
      !alert ||
      !Number.isSafeInteger(alert.incident_id) ||
      alert.incident_id <= 0
    ) {
      continue;
    }

    merged.set(alert.incident_id, alert);
  }

  return Array.from(merged.values())
    .sort((a, b) => {
      const aTime = Date.parse(a.detected_at) || 0;
      const bTime = Date.parse(b.detected_at) || 0;
      return bTime - aTime;
    })
    .slice(0, 100);
}
