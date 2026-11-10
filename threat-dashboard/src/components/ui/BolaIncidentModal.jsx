import { useEffect } from "react";
import {
  AlertTriangle,
  X,
  ShieldAlert,
  Clock3,
  Globe,
  FileSearch,
} from "lucide-react";

function getText(value, fallback = "Not available") {
  if (
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.trim() === "")
  ) {
    return fallback;
  }

  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  return fallback;
}

function formatTimestamp(value) {
  if (typeof value !== "string" || !value.trim()) {
    return "Not available";
  }

  return value.replace("T", " ").replace(/\.\d+$/, "");
}

export default function BolaIncidentModal({
  incident,
  onClose = () => {},
}) {
  useEffect(() => {
    if (!incident) return undefined;

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

  const severity = getText(incident.severity, "Unknown");
  const normalizedSeverity = severity.toLowerCase();

  const severityStyles = {
    critical: "bg-red-100 text-red-800",
    high: "bg-orange-100 text-orange-800",
    medium: "bg-amber-100 text-amber-800",
    low: "bg-blue-100 text-blue-800",
  };

  const severityClass =
    severityStyles[normalizedSeverity] || "bg-gray-100 text-gray-800";

  const details = [
    ["Incident ID", getText(incident.incident_id)],
    ["Detected At", formatTimestamp(incident.detected_at)],
    ["Severity", severity],
    ["Status", getText(incident.status)],
    ["Source IP", getText(incident.source_ip)],
    ["Transaction ID", getText(incident.transaction_id)],
    [
      "Endpoint ID",
      incident.endpoint_id === null
        ? "Not associated with a discovered endpoint"
        : getText(incident.endpoint_id),
    ],
  ];

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
        aria-labelledby="incident-modal-title"
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
                Backend Security Alert
              </p>

              <h2
                id="incident-modal-title"
                className="mt-1 text-xl font-bold text-gray-900"
              >
                {getText(incident.title, "Security incident")}
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Incident #{getText(incident.incident_id)}
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
              {getText(incident.status, "Unknown status")}
            </span>

            <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
              Potential finding
            </span>
          </div>

          {/* Backend-provided fields */}
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

          {/* Backend description */}
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
            <div className="flex items-center gap-2">
              <FileSearch size={18} className="text-gray-500" />
              <h3 className="text-sm font-semibold text-gray-900">
                Backend Detection Description
              </h3>
            </div>

            <p className="mt-2 break-words text-sm leading-6 text-gray-700">
              {getText(
                incident.description,
                "The backend did not provide a detection description."
              )}
            </p>
          </div>

          {/* Investigation limitation */}
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <div className="flex items-center gap-2">
              <AlertTriangle
                size={18}
                className="shrink-0 text-amber-700"
              />

              <h3 className="text-sm font-semibold text-amber-900">
                Investigation Required
              </h3>
            </div>

            <p className="mt-2 text-sm leading-6 text-amber-900">
              This is a heuristic detection, not proof of a confirmed
              vulnerability. Verify the authenticated identity, token
              validity, resource ownership, and server-side authorization
              decision using approved test evidence and backend logs.
            </p>
          </div>

          {/* Investigation guidance */}
          <div className="space-y-3 rounded-xl border border-gray-200 p-4">
            <div className="flex items-start gap-3">
              <Globe
                size={17}
                className="mt-0.5 shrink-0 text-gray-400"
              />

              <div>
                <p className="text-xs text-gray-500">
                  Source address
                </p>

                <p className="mt-1 break-all text-sm text-gray-800">
                  {getText(incident.source_ip)}
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
                  Investigation guidance
                </p>

                <p className="mt-1 text-sm leading-5 text-gray-800">
                  Use transaction ID {getText(incident.transaction_id)}
                  {" "}to correlate this alert with available transaction
                  evidence. Confirm whether the response exposed an object
                  belonging to another authenticated user.
                </p>
              </div>
            </div>
          </div>

          <p className="text-xs leading-5 text-gray-500">
            This view displays persisted backend alert data. It does not
            independently validate the detection or change backend
            enforcement.
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
