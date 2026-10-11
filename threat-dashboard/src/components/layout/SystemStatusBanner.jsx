
export default function SystemStatusBanner({
  connectionStatus = "disconnected",
  latestMessage,
  lastError,
  isMockMode = false,
}) {
  const statusLabels = {
    connected: "Connected to backend",
    connecting: "Connecting to backend...",
    disconnected: "Backend disconnected",
    error: "Connection error",
    mock: "Mock telemetry active",
  };

  const statusLabel =
    statusLabels[connectionStatus] ||
    "Unknown connection status";

  const statusColor =
    connectionStatus === "connected"
      ? "bg-green-500"
      : connectionStatus === "mock"
        ? "bg-amber-500"
        : connectionStatus === "error"
          ? "bg-red-500"
          : "bg-slate-400";

  return (
    <section
      className="mb-6 rounded-xl border border-slate-200 bg-white p-4"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`h-2.5 w-2.5 rounded-full ${statusColor}`}
        />

        <h2 className="font-semibold text-slate-900">
          {statusLabel}
        </h2>
      </div>

      {isMockMode && (
        <p className="mt-2 text-sm font-medium text-amber-700">
          MOCK DATA — TEMPORARY. These events are simulated,
          not live security detections.
        </p>
      )}

      {!isMockMode && connectionStatus !== "connected" && (
        <p className="mt-2 text-sm text-slate-600">
          Live backend telemetry is not currently available.
        </p>
      )}

      {lastError && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {lastError}
        </p>
      )}

      {latestMessage && (
        <p className="mt-2 break-words text-sm text-slate-600">
          Latest message received:{" "}
          {typeof latestMessage.type === "string"
            ? latestMessage.type
            : "Telemetry event"}
        </p>
      )}
    </section>
  );
}
