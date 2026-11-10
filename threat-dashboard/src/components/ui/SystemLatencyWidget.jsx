
import { Activity, Clock3, Gauge, Wifi } from "lucide-react";

export default function SystemLatencyWidget({
  latencyMs = null,
  isMock = true,
  source = "",
}) {
  const hasLatency =
    typeof latencyMs === "number" &&
    Number.isFinite(latencyMs) &&
    latencyMs >= 0;

  const displayedLatency = hasLatency ? latencyMs : null;

  const statusLabel = isMock
    ? "Demo data"
    : hasLatency
      ? "Reported value"
      : "Not available";

  const statusColor = isMock
    ? "text-amber-700 bg-amber-50"
    : hasLatency
      ? "text-blue-700 bg-blue-50"
      : "text-slate-600 bg-slate-100";

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-labelledby="system-latency-title"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-50 p-2.5">
            <Gauge
              className="h-5 w-5 text-indigo-600"
              aria-hidden="true"
            />
          </div>

          <div>
            <h2
              id="system-latency-title"
              className="text-base font-semibold text-slate-900"
            >
              Telemetry Latency Value
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Latency reported by the latest valid telemetry event
            </p>
          </div>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${statusColor}`}
        >
          <Activity
            className="h-3.5 w-3.5"
            aria-hidden="true"
          />
          {statusLabel}
        </span>
      </div>

      <div className="mt-6 flex items-end gap-2">
        {displayedLatency !== null ? (
          <>
            <span className="text-4xl font-bold tracking-tight text-slate-900">
              {displayedLatency.toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
            </span>

            <span className="mb-1 text-sm font-medium text-slate-500">
              ms
            </span>
          </>
        ) : (
          <span className="text-xl font-semibold text-slate-500">
            Not available
          </span>
        )}
      </div>

      <div className="mt-4 flex items-start gap-2 border-t border-slate-100 pt-4">
        {isMock ? (
          <Clock3
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
            aria-hidden="true"
          />
        ) : (
          <Wifi
            className="mt-0.5 h-4 w-4 shrink-0 text-slate-500"
            aria-hidden="true"
          />
        )}

        <div>
          <p className="text-sm text-slate-600">
            {isMock
              ? "Simulated value. This is not a measured system latency."
              : displayedLatency !== null
                ? "Value received in telemetry. The measurement boundary has not been independently verified."
                : "No valid latency value is available."}
          </p>

          {source && (
            <p className="mt-1 break-words text-xs text-slate-400">
              Source: {source}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
