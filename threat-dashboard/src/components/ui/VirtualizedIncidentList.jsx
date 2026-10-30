
import { useMemo, useState } from "react";
import { List } from "react-window";
import { Activity, Search } from "lucide-react";

const DEMO_INCIDENT_COUNT = 1000;

const SEVERITIES = ["High", "Medium", "Low"];
const METHODS = ["GET", "POST", "PUT", "DELETE"];

const ENDPOINTS = [
  "/api/v1/users",
  "/api/v1/auth/login",
  "/api/v1/products",
  "/api/internal/debug",
  "/api/v1/reports/export",
];

function createDemoIncidents() {
  return Array.from({ length: DEMO_INCIDENT_COUNT }, (_, index) => ({
    id: `DEMO-INC-${String(index + 1).padStart(4, "0")}`,
    method: METHODS[index % METHODS.length],
    endpoint: ENDPOINTS[index % ENDPOINTS.length],
    severity: SEVERITIES[index % SEVERITIES.length],
    status: index % 3 === 0 ? "Investigating" : "Detected",
  }));
}

function IncidentRow({
  index,
  style,
  incidents,
  onSelect,
  ariaAttributes,
}) {
  const incident = incidents[index];

  if (!incident) {
    return null;
  }

  const severityClasses = {
    High: "border-red-200 bg-red-50 text-red-700",
    Medium: "border-amber-200 bg-amber-50 text-amber-700",
    Low: "border-sky-200 bg-sky-50 text-sky-700",
  };

  return (
    <div {...ariaAttributes} style={style} className="px-2">
      <button
        type="button"
        onClick={() => onSelect(incident)}
        className="grid h-[56px] w-full grid-cols-1 items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 text-left transition-colors hover:border-indigo-300 hover:bg-gray-50 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_100px_130px] sm:gap-3"
        aria-label={`Inspect ${incident.id}, ${incident.severity} severity`}
      >
        <span className="truncate text-xs font-semibold text-gray-800">
          {incident.id}
        </span>

        <span className="truncate text-xs text-gray-600">
          <span className="mr-2 font-semibold text-indigo-600">
            {incident.method}
          </span>
          {incident.endpoint}
        </span>

        <span
          className={`w-fit rounded-full border px-2 py-1 text-[10px] font-semibold ${severityClasses[incident.severity]}`}
        >
          {incident.severity}
        </span>

        <span className="hidden text-xs text-gray-500 sm:block">
          {incident.status}
        </span>
      </button>
    </div>
  );
}

export default function VirtualizedIncidentList() {
  const incidents = useMemo(() => createDemoIncidents(), []);

  const [selectedIncident, setSelectedIncident] = useState(null);
  const [search, setSearch] = useState("");

  const filteredIncidents = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return incidents;
    }

    return incidents.filter((incident) =>
      [
        incident.id,
        incident.method,
        incident.endpoint,
        incident.severity,
        incident.status,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [incidents, search]);

  const rowProps = useMemo(
    () => ({
      incidents: filteredIncidents,
      onSelect: setSelectedIncident,
    }),
    [filteredIncidents],
  );

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 text-gray-900 shadow-sm sm:p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-indigo-600" />

            <h2 className="text-base font-semibold text-gray-900">
              Virtualized Incident List
            </h2>
          </div>

          <p className="mt-1 text-xs text-gray-500">
            Performance demonstration using synthetic data only.
          </p>
        </div>

        <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
          {filteredIncidents.length.toLocaleString()} of{" "}
          {incidents.length.toLocaleString()} incidents
        </span>
      </div>

      <label
        htmlFor="virtual-incident-search"
        className="mb-3 flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100"
      >
        <Search size={16} className="shrink-0 text-gray-400" />

        <input
          id="virtual-incident-search"
          name="virtual-incident-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search ID, endpoint, method, severity, status..."
          className="min-w-0 flex-1 bg-transparent py-3 text-sm text-gray-900 outline-none placeholder:text-gray-400"
        />
      </label>

      {filteredIncidents.length > 0 ? (
        <List
          rowComponent={IncidentRow}
          rowCount={filteredIncidents.length}
          rowHeight={64}
          rowProps={rowProps}
          defaultHeight={384}
          overscanCount={5}
          style={{ width: "100%", height: 384 }}
        />
      ) : (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center text-sm text-gray-500">
          No matching demo incidents.
        </div>
      )}

      <p className="mt-3 text-xs leading-5 text-gray-500">
        DEMO DATA — These incidents are generated in the browser. They are
        not real security incidents and are not connected to live backend
        telemetry.
      </p>

      {selectedIncident && (
        <div
          className="mt-4 rounded-lg border border-indigo-200 bg-gray-50 p-4"
          aria-live="polite"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">
                Selected demo incident
              </h3>

              <p className="mt-2 text-sm text-gray-800">
                {selectedIncident.id} · {selectedIncident.severity}
              </p>

              <p className="mt-1 break-all text-xs text-gray-600">
                {selectedIncident.method} {selectedIncident.endpoint}
              </p>

              <p className="mt-1 text-xs text-gray-600">
                Status: {selectedIncident.status}
              </p>
            </div>

            <button
              type="button"
              onClick={() => setSelectedIncident(null)}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-xs text-gray-700 hover:bg-gray-100"
            >
              Close details
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
