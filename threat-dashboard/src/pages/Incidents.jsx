
import { useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  ShieldAlert,
  Search,
} from "lucide-react";
import BolaIncidentModal from "../components/ui/BolaIncidentModal";

const demoIncidents = [
  {
    id: "DEMO-BOLA-001",
    type: "BOLA",
    title: "Possible object-level authorization issue",
    severity: "High",
    method: "GET",
    endpoint: "/api/v1/accounts/{id}",
    timestamp: "Sample event",
    status: "Under investigation",
  },
];

export default function Incidents() {
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");

  const filteredIncidents = demoIncidents.filter((incident) => {
    const searchableText = [
      incident.id,
      incident.title,
      incident.type,
      incident.severity,
      incident.endpoint,
      incident.status,
    ]
      .join(" ")
      .toLowerCase();

    return searchableText.includes(searchTerm.toLowerCase());
  });

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div>
        <div className="flex items-center gap-2">
          <ShieldAlert size={25} className="text-indigo-600" />

          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            Security Incidents
          </h1>
        </div>

        <p className="mt-2 text-sm text-gray-500">
          Review and inspect security events detected by API Sentinel.
        </p>
      </div>

      {/* Demo warning */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm font-semibold text-amber-900">
          Demonstration incident data
        </p>

        <p className="mt-1 text-sm leading-5 text-amber-800">
          These incidents are simulated for the Day 9 UI task.
          They are not confirmed findings from your backend.
        </p>
      </div>

      {/* Incident summary */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-500">Total Incidents</p>

          <p className="mt-2 text-2xl font-bold text-gray-900">
            {demoIncidents.length}
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-500">High Severity</p>

          <p className="mt-2 text-2xl font-bold text-orange-600">
            {
              demoIncidents.filter(
                (incident) =>
                  incident.severity.toLowerCase() === "high"
              ).length
            }
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-500">Under Investigation</p>

          <p className="mt-2 text-2xl font-bold text-indigo-600">
            {
              demoIncidents.filter(
                (incident) =>
                  incident.status === "Under investigation"
              ).length
            }
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search
          size={18}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
        />

        <input
          id="incident-search"
          name="incidentSearch"
          type="search"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder="Search incidents by ID, severity, endpoint..."
          aria-label="Search incidents"
          className="w-full rounded-xl border border-gray-200 bg-white py-3 pl-10 pr-4 text-sm text-gray-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
      </div>

      {/* Incident list */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            Incident List
          </h2>

          <span className="text-sm text-gray-500">
            {filteredIncidents.length}{" "}
            {filteredIncidents.length === 1 ? "incident" : "incidents"}
          </span>
        </div>

        {filteredIncidents.length > 0 ? (
          filteredIncidents.map((incident) => (
            <article
              key={incident.id}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:shadow-md sm:p-6"
            >
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="shrink-0 rounded-lg bg-red-50 p-3 text-red-600">
                    <AlertTriangle size={22} />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-gray-900">
                        {incident.title}
                      </h3>

                      <span className="rounded-full bg-orange-100 px-2.5 py-1 text-xs font-semibold text-orange-800">
                        {incident.severity}
                      </span>

                      <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-700">
                        {incident.type}
                      </span>
                    </div>

                    <p className="mt-3 text-sm text-gray-500">
                      Incident ID: {incident.id}
                    </p>

                    <p className="mt-2 break-all font-mono text-xs text-gray-700">
                      {incident.method} {incident.endpoint}
                    </p>

                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                      <p className="text-xs text-gray-500">
                        Detected: {incident.timestamp}
                      </p>

                      <p className="text-xs text-gray-500">
                        Status: {incident.status}
                      </p>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setSelectedIncident(incident)}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                >
                  View Details
                  <ArrowUpRight size={16} />
                </button>
              </div>
            </article>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center">
            <Search
              size={24}
              className="mx-auto text-gray-400"
            />

            <h3 className="mt-3 font-semibold text-gray-900">
              No incidents found
            </h3>

            <p className="mt-1 text-sm text-gray-500">
              Try another search term.
            </p>
          </div>
        )}
      </section>

      {/* Incident details modal */}
      <BolaIncidentModal
        incident={selectedIncident}
        onClose={() => setSelectedIncident(null)}
      />
    </div>
  );
}
