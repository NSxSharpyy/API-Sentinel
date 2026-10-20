
import {
  Activity,
  Clock3,
  Globe,
  ShieldAlert,
} from "lucide-react";

import SeverityBadge from "./SeverityBadge";

function formatTimestamp(timestamp) {
  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Timestamp unavailable";
  }

  return (
    new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }).format(date) + " UTC"
  );
}

export default function IncidentAlertCard({ incident }) {
  if (!incident || typeof incident !== "object") {
    return null;
  }

  const {
    id,
    title,
    severity,
    attackType,
    endpoint,
    method,
    statusCode,
    timestamp,
    description,
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
              {id || "Incident ID unavailable"}
            </p>

            <h3 className="mt-1 break-words text-sm font-semibold leading-5 text-gray-900">
              {title || "Untitled incident"}
            </h3>
          </div>
        </div>

        <SeverityBadge severity={severity} />
      </div>

      <p className="mt-4 text-sm leading-6 text-gray-600">
        {description || "No description available."}
      </p>

      <div className="mt-4 space-y-3 border-t border-gray-100 pt-4">
        <div className="flex items-start gap-2 text-sm">
          <Activity
            size={16}
            className="mt-0.5 shrink-0 text-gray-500"
            aria-hidden="true"
          />

          <div className="min-w-0">
            <p className="text-xs text-gray-500">
              Attack type
            </p>
            <p className="break-words font-medium text-gray-800">
              {attackType || "Unknown"}
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
            <p className="text-xs text-gray-500">Endpoint</p>
            <p className="break-all font-mono text-xs text-gray-800">
              {endpoint || "Endpoint unavailable"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
          <span className="rounded bg-gray-100 px-2 py-1 font-semibold">
            {method || "N/A"}
          </span>

          <span>
            HTTP {Number.isInteger(statusCode) ? statusCode : "N/A"}
          </span>
        </div>
      </div>

      <div className="mt-auto flex items-start gap-2 border-t border-gray-100 pt-4 text-xs text-gray-500">
        <Clock3
          size={15}
          className="mt-0.5 shrink-0"
          aria-hidden="true"
        />

        <time dateTime={timestamp || undefined}>
          {timestamp
            ? formatTimestamp(timestamp)
            : "Timestamp unavailable"}
        </time>
      </div>
    </article>
  );
}
