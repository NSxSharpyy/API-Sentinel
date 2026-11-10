
import { Activity, Clock3 } from "lucide-react";

function AlertResponsivenessMonitor({
  latestLatencyMs = null,
  measurementSource = "Waiting for telemetry timing",
}) {
  const hasMeasurement =
    typeof latestLatencyMs === "number" &&
    Number.isFinite(latestLatencyMs) &&
    latestLatencyMs >= 0;

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-labelledby="alert-responsiveness-title"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-50 p-2.5">
            <Activity
              className="h-5 w-5 text-indigo-600"
              aria-hidden="true"
            />
          </div>

          <div>
            <h2
              id="alert-responsiveness-title"
              className="font-semibold text-slate-900"
            >
              Alert Responsiveness
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Event receipt to alert render
            </p>
          </div>
        </div>

        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            hasMeasurement
              ? "bg-emerald-50 text-emerald-700"
              : "bg-slate-100 text-slate-600"
          }`}
        >
          {hasMeasurement ? "Measured" : "Not measured"}
        </span>
      </div>

      <div className="mt-6 flex items-end gap-2">
        {hasMeasurement ? (
          <>
            <span className="text-4xl font-bold tracking-tight text-slate-900">
              {latestLatencyMs.toFixed(2)}
            </span>

            <span className="mb-1 text-sm text-slate-500">
              ms
            </span>
          </>
        ) : (
          <span className="text-xl font-semibold text-slate-500">
            Awaiting measurement
          </span>
        )}
      </div>

      <div className="mt-4 flex items-start gap-2 border-t border-slate-100 pt-4">
        <Clock3
          className="mt-0.5 h-4 w-4 shrink-0 text-slate-400"
          aria-hidden="true"
        />

        <p className="break-words text-sm text-slate-500">
          {measurementSource}
        </p>
      </div>
    </section>
  );
}

export default AlertResponsivenessMonitor;
