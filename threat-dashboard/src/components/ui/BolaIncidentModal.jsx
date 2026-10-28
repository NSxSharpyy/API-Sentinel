
import { useEffect } from "react";
import {
  AlertTriangle,
  X,
  ShieldAlert,
  Clock3,
  Globe,
  FileSearch,
} from "lucide-react";

function getText(value, fallback) {
  if (
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.trim() === "")
  ) {
    return fallback;
  }

  if (
    typeof value === "string" ||
    typeof value === "number"
  ) {
    return String(value);
  }

  return fallback;
}

export default function BolaIncidentModal({
  incident,
  onClose = () => {},
}) {
  useEffect(() => {
    if (!incident) return;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [incident, onClose]);

  if (!incident || typeof incident !== "object") {
    return null;
  }

  const severity = getText(incident.severity, "High");
  const normalizedSeverity = severity.toLowerCase();

  const severityStyles = {
    critical: "bg-red-100 text-red-800",
    high: "bg-orange-100 text-orange-800",
    medium: "bg-amber-100 text-amber-800",
    low: "bg-blue-100 text-blue-800",
  };

  const severityClass =
    severityStyles[normalizedSeverity] ||
    "bg-gray-100 text-gray-800";

  const incidentId = getText(incident.id, "DEMO-BOLA-001");
  const method = getText(incident.method, "GET");
  const endpoint = getText(
    incident.endpoint,
    "/api/v1/accounts/{id}"
  );
  const timestamp = getText(
    incident.timestamp,
    "Sample event"
  );
  const status = getText(
    incident.status,
    "Under investigation"
  );

  const details = [
    ["Incident ID", incidentId],
    ["HTTP Method", method],
    ["Endpoint", endpoint],
    ["Detected At", timestamp],
    ["Status", status],
  ];

  const payload =
    incident.payload &&
    typeof incident.payload === "object" &&
    !Array.isArray(incident.payload)
      ? incident.payload
      : {};

  const headers =
    payload.headers &&
    typeof payload.headers === "object" &&
    !Array.isArray(payload.headers)
      ? payload.headers
      : {};

  const targetUser = getText(
    payload.target_user_id,
    "Unknown User"
  );

  // Never render the authorization header or token itself.
  const hasAuthorizationHeader = Object.keys(headers).some(
    (key) => key.toLowerCase() === "authorization"
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/60 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="bola-modal-title"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-red-50 p-3 text-red-600">
              <ShieldAlert size={24} />
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-red-600">
                Security Incident · BOLA
              </p>

              <h2
                id="bola-modal-title"
                className="mt-1 text-xl font-bold text-gray-900"
              >
                Broken Object Level Authorization
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Detailed incident inspection
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close incident details"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <X size={20} />
          </button>
        </div>

        <div className="space-y-6 p-5 sm:p-6">
          {/* Severity and status */}
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ${severityClass}`}
            >
              {severity} Severity
            </span>

            <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
              {status}
            </span>

            <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
              Mock incident
            </span>
          </div>

          {/* Incident information */}
          <div>
            <h3 className="mb-3 text-sm font-semibold text-gray-900">
              Incident Information
            </h3>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {details.map(([label, value]) => (
                <div
                  key={label}
                  className="min-w-0 rounded-lg border border-gray-200 bg-gray-50 p-3"
                >
                  <p className="text-xs font-medium text-gray-500">
                    {label}
                  </p>

                  <p className="mt-1 break-words text-sm font-semibold text-gray-900">
                    {value}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Reason for flagging */}
          <div className="rounded-xl border border-red-200 bg-red-50 p-4">
            <div className="flex items-center gap-2">
              <AlertTriangle
                size={18}
                className="shrink-0 text-red-600"
              />

              <h3 className="text-sm font-semibold text-red-900">
                Why was this flagged?
              </h3>
            </div>

            <p className="mt-2 text-sm leading-6 text-red-900">
              This simulated event suggests that object-level
              authorization may not have been correctly enforced
              for a requested resource. The backend must verify
              that the authenticated user is authorized to access
              that specific object before this is treated as a
              confirmed vulnerability.
            </p>
          </div>

          {/* Request inspection */}
          <div>
            <div className="mb-3 flex items-center gap-2">
              <FileSearch size={18} className="text-gray-500" />

              <h3 className="text-sm font-semibold text-gray-900">
                Request Inspection
              </h3>
            </div>

            <div className="space-y-4 rounded-xl border border-gray-200 p-4">
              <div className="flex items-start gap-3">
                <Globe
                  size={17}
                  className="mt-0.5 shrink-0 text-gray-400"
                />

                <div>
                  <p className="text-xs text-gray-500">
                    Request context
                  </p>

                  <p className="mt-1 text-sm text-gray-800">
                    Simulated API request; no live request was inspected.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <Clock3
                  size={17}
                  className="mt-0.5 shrink-0 text-gray-400"
                />

                <div>
                  <p className="text-xs text-gray-500">
                    Investigation note
                  </p>

                  <p className="mt-1 text-sm leading-5 text-gray-800">
                    Verify the authenticated identity, resource
                    ownership, and authorization decision using
                    approved backend logs and test evidence.
                  </p>
                </div>
              </div>

              <div className="border-t border-gray-100 pt-3">
                <p className="text-xs font-medium text-gray-500">
                  Request method
                </p>

                <p className="mt-1 font-mono text-sm text-gray-900">
                  {method}
                </p>

                <p className="mt-3 text-xs font-medium text-gray-500">
                  Request endpoint
                </p>

                <p className="mt-1 break-all font-mono text-sm text-gray-900">
                  {endpoint}
                </p>
              </div>

              {/* Safe payload details */}
              <div className="border-t border-gray-100 pt-3">
                <p className="text-xs font-medium text-gray-500">
                  Target user ID
                </p>

                <p className="mt-1 break-words font-mono text-sm text-gray-900">
                  {targetUser}
                </p>

                <p className="mt-3 text-xs font-medium text-gray-500">
                  Authorization header
                </p>

                <p className="mt-1 text-sm text-gray-800">
                  {hasAuthorizationHeader
                    ? "Present (value hidden for security)"
                    : "Not available"}
                </p>
              </div>
            </div>
          </div>

          <p className="text-xs leading-5 text-gray-500">
            Demo UI only. This modal does not confirm a real attack,
            retrieve production payloads, or change backend enforcement.
          </p>
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-gray-200 bg-gray-50 p-4 sm:px-6">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Close Details
          </button>
        </div>
      </section>
    </div>
  );
}
