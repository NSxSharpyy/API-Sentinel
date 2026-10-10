
import { mockIncidents } from "../data/mockIncidents";
import IncidentAlertGrid from "../components/ui/IncidentAlertGrid";

export default function Dashboard() {
  const incidents = mockIncidents;

  const criticalCount = incidents.filter(
    (incident) =>
      incident.severity?.toLowerCase() === "critical"
  ).length;

  const highCount = incidents.filter(
    (incident) =>
      incident.severity?.toLowerCase() === "high"
  ).length;

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          Security Overview
        </h1>

        <p className="mt-1 text-sm text-gray-600">
          Security incident monitoring and alert summaries.
        </p>

        <p className="mt-2 text-xs font-medium text-amber-700">
          DEMO DATA — Not connected to live telemetry
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">
            Critical incidents
          </p>

          <p className="mt-2 text-3xl font-bold text-red-700">
            {criticalCount}
          </p>

          <p className="mt-1 text-xs text-gray-500">
            Count within the temporary demo dataset
          </p>
        </article>

        <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">
            High-severity incidents
          </p>

          <p className="mt-2 text-3xl font-bold text-orange-700">
            {highCount}
          </p>

          <p className="mt-1 text-xs text-gray-500">
            Count within the temporary demo dataset
          </p>
        </article>
      </div>

      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Recent Security Alerts
          </h2>

          <p className="mt-1 text-sm text-gray-600">
            Illustrative incidents showing the reusable alert
            card and severity components.
          </p>
        </div>

        <IncidentAlertGrid incidents={incidents} />
      </section>
    </section>
  );
}
