import {
  Clock3,
  Globe,
  ShieldAlert,
  Activity,
} from "lucide-react";

import SeverityBadge from "./SeverityBadge";

function formatTimestamp(value) {
  if (typeof value !== "string" || !value.trim()) {
    return "Timestamp unavailable";
  }

  // Backend timestamps do not specify a timezone. Preserve the supplied time.
  return value.replace("T", " ").replace(/\.\d+$/, "");
}

export default function IncidentAlertCard({ incident }) {
  if (!incident || typeof incident !== "object") {
    return null;
  }

  const {
    incident_id,
    title,
    severity,
    description,
    detected_at,
    source_ip,
    transaction_id,
    endpoint_id,
    status,
  } = incident;

  return (
    <article className="flex h-full flex-col rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-lg bg-gray-100 p-2">
            <ShieldAlert
              size={20}
              className="text-gray-700"
              aria-hidden="true"
            />
          </div>

          <div className="min-w-0">
            <p className="text-xs font-medium text-gray-500">
              Incident #{incident_id ?? "Unavailable"}
            </p>

            <h3 className="mt-1 break-words text-sm font-semibold leading-5 text-gray-900">
              {title || "Untitled backend alert"}
            </h3>
          </div>
        </div>

        <SeverityBadge severity={severity} />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
          Potential finding
        </span>

        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-700">
          {status || "Unknown status"}
        </span>
      </div>

      <p className="mt-4 break-words text-sm leading-6 text-gray-600">
        {description || "No description available."}
      </p>

      <div className="mt-4 space-y-3 border-t border-gray-100 pt-4">
        <div className="flex items-start gap-2 text-sm">
          <Globe
            size={16}
            className="mt-0.5 shrink-0 text-gray-500"
            aria-hidden="true"
          />

          <div className="min-w-0">
            <p className="text-xs text-gray-500">Source IP</p>
            <p className="break-all font-medium text-gray-800">
              {source_ip || "Not available"}
            </p>
          </div>
        </div>

        <div className="flex items-start gap-2 text-sm">
          <Activity
            size={16}
            className="mt-0.5 shrink-0 text-gray-500"
            aria-hidden="true"
          />

          <div className="min-w-0">
            <p className="text-xs text-gray-500">Transaction ID</p>
            <p className="font-medium text-gray-800">
              {transaction_id ?? "Not linked"}
            </p>
          </div>
        </div>

        <div className="flex items-start gap-2 text-sm">
          <Globe
            size={16}
            className="mt-0.5 shrink-0 text-gray-500"
            aria-hidden="true"
          />

          <div className="min-w-0">
            <p className="text-xs text-gray-500">Endpoint ID</p>
            <p className="break-words font-medium text-gray-800">
              {endpoint_id ?? "Not associated"}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-auto flex items-start gap-2 border-t border-gray-100 pt-4 text-xs text-gray-500">
        <Clock3
          size={15}
          className="mt-0.5 shrink-0"
          aria-hidden="true"
        />

        <time dateTime={detected_at || undefined}>
          {formatTimestamp(detected_at)}
        </time>
      </div>
    </article>
  );
}
