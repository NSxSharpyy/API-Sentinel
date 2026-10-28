
import { useLayoutEffect } from "react";
import { Activity, Clock3 } from "lucide-react";

export default function TelemetryRenderProbe({
  event = null,
  onRendered,
}) {
  const eventId = event?.id;
  const receivedAtMs = event?.receivedAtMs;
  const telemetrySource = event?.telemetrySource;
  const method = event?.method;
  const endpoint = event?.endpoint;
  const statusCode = event?.statusCode;

  useLayoutEffect(() => {
    if (
      eventId === null ||
      eventId === undefined ||
      typeof receivedAtMs !== "number" ||
      !Number.isFinite(receivedAtMs) ||
      typeof onRendered !== "function"
    ) {
      return;
    }

    const latencyMs = performance.now() - receivedAtMs;

    if (!Number.isFinite(latencyMs) || latencyMs < 0) {
      return;
    }

    onRendered(
      eventId,
      receivedAtMs,
      latencyMs,
      telemetrySource
    );
  }, [
    eventId,
    receivedAtMs,
    telemetrySource,
    onRendered,
  ]);

  if (!event) {
    return (
      <section className="rounded-xl border border-dashed border-slate-300 bg-white p-5">
        <div className="flex items-center gap-2">
          <Clock3
            className="h-5 w-5 text-slate-400"
            aria-hidden="true"
          />
          <h2 className="font-semibold text-slate-900">
            Latest Telemetry Event
          </h2>
        </div>

        <p className="mt-2 text-sm text-slate-500">
          Waiting for a valid telemetry event.
        </p>
      </section>
    );
  }

  const isMock = telemetrySource === "mock";

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-labelledby="latest-telemetry-event-title"
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
              id="latest-telemetry-event-title"
              className="font-semibold text-slate-900"
            >
              Latest Telemetry Event
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Event rendered in the dashboard
            </p>
          </div>
        </div>

        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            isMock
              ? "bg-amber-50 text-amber-700"
              : "bg-emerald-50 text-emerald-700"
          }`}
        >
          {isMock ? "Mock event" : "Live telemetry"}
        </span>
      </div>

      <dl className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium text-slate-500">
            Event ID
          </dt>
          <dd className="mt-1 break-all text-sm font-semibold text-slate-900">
            {String(eventId)}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-medium text-slate-500">
            Endpoint
          </dt>
          <dd className="mt-1 break-all text-sm font-semibold text-slate-900">
            {method} {endpoint}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-medium text-slate-500">
            HTTP status
          </dt>
          <dd className="mt-1 text-sm text-slate-700">
            {statusCode ?? "Not provided"}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-medium text-slate-500">
            Measurement type
          </dt>
          <dd className="mt-1 text-sm text-slate-700">
            {isMock
              ? "Simulated telemetry"
              : "Received WebSocket telemetry"}
          </dd>
        </div>
      </dl>

      <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
        {isMock
          ? "This is a simulated telemetry event, not proof of a real attack."
          : "This event came from the configured telemetry connection. Its security significance must be validated separately."}
      </p>
    </section>
  );
}
