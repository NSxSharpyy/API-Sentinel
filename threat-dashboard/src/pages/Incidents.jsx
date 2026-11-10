import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import {
  AlertTriangle,
  ArrowUpRight,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";
import BolaIncidentModal from "../components/ui/BolaIncidentModal";
import { getAlerts } from "../services/apiClient";
import { mergeAlerts } from "../utils/alerts";

function formatTimestamp(value) {
  if (typeof value !== "string" || !value.trim()) {
    return "Not available";
  }

  // Preserve the backend timestamp; it does not include timezone metadata.
  return value.replace("T", " ").replace(/\.\d+$/, "");
}

export default function Incidents() {
  const [incidents, setIncidents] = useState([]);
  const [totalIncidents, setTotalIncidents] = useState(0);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const { liveAlerts = [] } = useOutletContext();

  useEffect(() => {
    const controller = new AbortController();

    async function loadIncidents() {
      setLoading(true);
      setError("");

      try {
        const response = await getAlerts({
          limit: 100,
          offset: 0,
          signal: controller.signal,
        });

        setIncidents(response.items);
        setTotalIncidents(response.total);
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load security incidents."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    loadIncidents();

    return () => controller.abort();
  }, [refreshKey]);

  const mergedIncidents = mergeAlerts(incidents, liveAlerts);

  const additionalLiveIncidentCount = liveAlerts.filter(
    (liveAlert) =>
      !incidents.some(
        (restIncident) =>
          restIncident.incident_id === liveAlert.incident_id
      )
  ).length;

  const displayedTotalIncidents =
    totalIncidents + additionalLiveIncidentCount;

  const filteredIncidents = mergedIncidents.filter((incident) => {
    const searchableText = [
      incident.incident_id,
      incident.title,
      incident.description,
      incident.severity,
      incident.source_ip,
      incident.transaction_id,
      incident.status,
    ]
      .map((value) => value ?? "")
      .join(" ")
      .toLowerCase();

    return searchableText.includes(searchTerm.trim().toLowerCase());
  });

  const highSeverityCount = mergedIncidents.filter(
    (incident) => String(incident.severity).toLowerCase() === "high"
  ).length;

  const openIncidentCount = mergedIncidents.filter(
    (incident) => String(incident.status).toLowerCase() === "open"
  ).length;

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
          Security alerts retrieved from the API-Sentinel backend.
        </p>
      </div>

      {/* Detection limitations */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm font-semibold text-amber-900">
          Potential security findings — lab heuristic
        </p>

        <p className="mt-1 text-sm leading-5 text-amber-800">
          Backend alerts are heuristic detections, not independently
          confirmed vulnerabilities. Verify the authenticated identity,
          resource ownership, and authorization evidence before treating
          an alert as a confirmed BOLA vulnerability.
        </p>
      </div>

      {/* Incident summary */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-500">Total Incidents</p>
          <p className="mt-2 text-2xl font-bold text-gray-900">
            {displayedTotalIncidents}
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-500">High Severity (loaded)</p>
          <p className="mt-2 text-2xl font-bold text-orange-600">
            {highSeverityCount}
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-500">Open Incidents (loaded)</p>
          <p className="mt-2 text-2xl font-bold text-indigo-600">
            {openIncidentCount}
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
          placeholder="Search incidents by ID, severity, source IP..."
          aria-label="Search incidents"
          className="w-full rounded-xl border border-gray-200 bg-white py-3 pl-10 pr-4 text-sm text-gray-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
      </div>

      {/* Incident list */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-gray-900">
            Incident List
          </h2>

          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-500">
              {filteredIncidents.length}{" "}
              {filteredIncidents.length === 1 ? "incident" : "incidents"}
            </span>

            <button
              type="button"
              onClick={() => setRefreshKey((value) => value + 1)}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw size={15} />
              Refresh
            </button>
          </div>
        </div>

        {loading ? (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
            Loading incidents from the backend...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6">
            <p className="font-semibold text-red-800">
              Unable to load incidents
            </p>
            <p className="mt-1 text-sm text-red-700">{error}</p>

            <button
              type="button"
              onClick={() => setRefreshKey((value) => value + 1)}
              className="mt-3 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800"
            >
              Try again
            </button>
          </div>
        ) : filteredIncidents.length > 0 ? (
          filteredIncidents.map((incident) => (
            <article
              key={incident.incident_id}
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
                        {incident.title || "Untitled backend alert"}
                      </h3>

                      <span className="rounded-full bg-orange-100 px-2.5 py-1 text-xs font-semibold text-orange-800">
                        {incident.severity || "Unknown severity"}
                      </span>

                      <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-700">
                        Potential finding
                      </span>
                    </div>

                    <p className="mt-3 text-sm text-gray-500">
                      Incident ID: {incident.incident_id}
                    </p>

                    <p className="mt-2 text-sm leading-6 text-gray-700">
                      {incident.description || "No description supplied."}
                    </p>

                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                      <p className="text-xs text-gray-500">
                        Detected: {formatTimestamp(incident.detected_at)}
                      </p>

                      <p className="text-xs text-gray-500">
                        Source IP: {incident.source_ip || "Not available"}
                      </p>

                      <p className="text-xs text-gray-500">
                        Transaction: {incident.transaction_id ?? "Not linked"}
                      </p>

                      <p className="text-xs text-gray-500">
                        Status: {incident.status || "Unknown"}
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
            <Search size={24} className="mx-auto text-gray-400" />

            <h3 className="mt-3 font-semibold text-gray-900">
              No incidents found
            </h3>

            <p className="mt-1 text-sm text-gray-500">
              {mergedIncidents.length === 0
                ? "The backend has not returned any incidents."
                : "Try another search term."}
            </p>
          </div>
        )}

        {!loading && !error && displayedTotalIncidents > mergedIncidents.length && (
          <p className="text-xs text-gray-500">
            Showing the first {mergedIncidents.length} of {displayedTotalIncidents} incidents.
            Pagination is not yet implemented.
          </p>
        )}
      </section>

      {/* Incident details */}
      <BolaIncidentModal
        incident={selectedIncident}
        onClose={() => setSelectedIncident(null)}
      />
    </div>
  );
}
