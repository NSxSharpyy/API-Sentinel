import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import IncidentAlertGrid from "../components/ui/IncidentAlertGrid";
import EndpointDataTable from "../components/ui/EndpointDataTable";
import AttackDistributionChart from "../components/ui/AttackDistributionChart";
import SystemLatencyWidget from "../components/ui/SystemLatencyWidget";
import AlertResponsivenessMonitor from "../components/ui/AlertResponsivenessMonitor";
import TelemetryRenderProbe from "../components/ui/TelemetryRenderProbe";
import EnforcementToggle from "../components/ui/EnforcementToggle";
import BlockedAttacksLiveStream from "../components/ui/BlockedAttacksLiveStream";
import VirtualizedIncidentList from "../components/ui/VirtualizedIncidentList";
import HighPriorityNotifications from "../components/ui/HighPriorityNotifications";

import { getAlerts, getMetrics } from "../services/apiClient";
import { mergeAlerts } from "../utils/alerts";

function formatMetric(value) {
  return Number.isFinite(value)
    ? value.toLocaleString("en-IN")
    : "—";
}

export default function Dashboard() {
  const {
    transactions = [],
    connectionStatus = "disconnected",
    isMockMode = false,
    latestLatencyMs = null,
    liveAlerts = [],
  } = useOutletContext();

  const [renderMeasurement, setRenderMeasurement] = useState(null);

  // Actual persisted backend data.
  const [backendAlerts, setBackendAlerts] = useState([]);
  const [alertsTotal, setAlertsTotal] = useState(null);
  const [backendMetrics, setBackendMetrics] = useState(null);

  const [backendLoading, setBackendLoading] = useState(true);
  const [backendErrors, setBackendErrors] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function loadBackendData() {
      setBackendLoading(true);
      setBackendErrors([]);

      const results = await Promise.allSettled([
        getAlerts({
          limit: 100,
          offset: 0,
          signal: controller.signal,
        }),
        getMetrics({ signal: controller.signal }),
      ]);

      if (controller.signal.aborted) {
        return;
      }

      const errors = [];

      const alertsResult = results[0];

      if (alertsResult.status === "fulfilled") {
        setBackendAlerts(alertsResult.value.items);
        setAlertsTotal(alertsResult.value.total);
      } else {
        errors.push(
          `Alerts API: ${
            alertsResult.reason instanceof Error
              ? alertsResult.reason.message
              : "Unable to load alerts."
          }`
        );
      }

      const metricsResult = results[1];

      if (metricsResult.status === "fulfilled") {
        setBackendMetrics(metricsResult.value);
      } else {
        errors.push(
          `Metrics API: ${
            metricsResult.reason instanceof Error
              ? metricsResult.reason.message
              : "Unable to load metrics."
          }`
        );
      }

      setBackendErrors(errors);
      setBackendLoading(false);
    }

    loadBackendData();

    return () => controller.abort();
  }, [refreshKey]);

  const handleEventRendered = useCallback(
    (eventId, receivedAtMs, latencyMs, source) => {
      setRenderMeasurement({
        eventId,
        receivedAtMs,
        latencyMs,
        source,
      });
    },
    [],
  );

  // Transactions are stored newest first by useTelemetry.
  const latestEvent = transactions[0] ?? null;

  const measurementMatchesLatestEvent =
    latestEvent !== null &&
    latestEvent.receivedAtMs !== null &&
    renderMeasurement?.eventId === latestEvent.id &&
    renderMeasurement?.receivedAtMs === latestEvent.receivedAtMs;

  const displayedRenderLatency = measurementMatchesLatestEvent
    ? renderMeasurement.latencyMs
    : null;

  const measurementSource = measurementMatchesLatestEvent
    ? renderMeasurement.source === "mock"
      ? "Mock telemetry: receipt-to-render measurement"
      : "Live telemetry: browser receipt-to-render measurement"
    : latestEvent
      ? "Measuring the latest telemetry event"
      : "Waiting for telemetry timing";

  const latencySource = isMockMode
    ? "Simulated telemetry value"
    : typeof latestLatencyMs === "number" &&
        Number.isFinite(latestLatencyMs) &&
        latestLatencyMs >= 0
      ? "Telemetry field; measurement boundary unverified"
      : "";

  // Read actual metric fields without inventing defaults.
  const databaseMetrics = backendMetrics?.database ?? {};
  const alertMetrics = backendMetrics?.alerts ?? {};
  const ingestionMetrics = backendMetrics?.ingestion ?? {};
  const persistenceMetrics = backendMetrics?.persistence ?? {};

  const mergedAlerts = mergeAlerts(backendAlerts, liveAlerts);

  const baselineIncidentCount =
    Number.isFinite(databaseMetrics.security_incidents)
      ? databaseMetrics.security_incidents
      : Number.isFinite(alertsTotal)
        ? alertsTotal
        : backendAlerts.length;

  const additionalLiveIncidentCount = liveAlerts.filter(
    (liveAlert) =>
      !backendAlerts.some(
        (restAlert) => restAlert.incident_id === liveAlert.incident_id
      )
  ).length;

  const totalIncidentCount =
    baselineIncidentCount + additionalLiveIncidentCount;

  const backendOpenCount = Number.isFinite(alertMetrics.open_incidents)
    ? alertMetrics.open_incidents
    : backendAlerts.filter(
        (alert) => String(alert.status).toLowerCase() === "open"
      ).length;

  const additionalLiveOpenCount = liveAlerts.filter(
    (liveAlert) =>
      String(liveAlert.status).toLowerCase() === "open" &&
      !backendAlerts.some(
        (restAlert) => restAlert.incident_id === liveAlert.incident_id
      )
  ).length;

  const openIncidentCount = backendOpenCount + additionalLiveOpenCount;
  const captureRunning = ingestionMetrics.capture_running;
  const persistenceWorkerRunning = persistenceMetrics.worker_running;

  return (
    <section className="space-y-6">
      {/* Dashboard heading */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            Security Overview
          </h1>

          <p className="mt-1 text-sm text-gray-600">
            Backend security metrics, persisted alerts, and telemetry status.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          disabled={backendLoading}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw size={15} />
          Refresh backend data
        </button>
      </div>

      {/* Mock telemetry limitation */}
      {isMockMode && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-900">
            Mock telemetry is active
          </p>

          <p className="mt-1 text-sm leading-5 text-amber-800">
            Transaction events, telemetry-based notifications, latency
            values, and responsiveness measurements are simulated.
            They are not evidence of live packet capture or real attacks.
          </p>
        </div>
      )}

      {/* Backend API errors */}
      {backendErrors.length > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4"
        >
          <p className="font-semibold text-red-800">
            Some backend data could not be loaded
          </p>

          {backendErrors.map((error) => (
            <p key={error} className="mt-1 text-sm text-red-700">
              {error}
            </p>
          ))}
        </div>
      )}

      {/* Actual backend metrics */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Backend Metrics
          </h2>

          <p className="mt-1 text-sm text-gray-500">
            Persisted database counts and current service state from
            the backend metrics API.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">
              Discovered endpoints
            </p>

            <p className="mt-2 text-3xl font-bold text-gray-900">
              {formatMetric(databaseMetrics.discovered_endpoints)}
            </p>

            <p className="mt-1 text-xs text-gray-500">
              Persisted endpoint records
            </p>
          </article>

          <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">
              Persisted transactions
            </p>

            <p className="mt-2 text-3xl font-bold text-gray-900">
              {formatMetric(databaseMetrics.transaction_logs)}
            </p>

            <p className="mt-1 text-xs text-gray-500">
              Historical database records
            </p>
          </article>

          <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">
              Security incidents
            </p>

            <p className="mt-2 text-3xl font-bold text-gray-900">
              {formatMetric(totalIncidentCount)}
            </p>

            <p className="mt-1 text-xs text-gray-500">
              Persisted backend alerts
            </p>
          </article>

          <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">
              Open incidents
            </p>

            <p className="mt-2 text-3xl font-bold text-indigo-700">
              {formatMetric(openIncidentCount)}
            </p>

            <p className="mt-1 text-xs text-gray-500">
              Backend-reported open alerts
            </p>
          </article>

          <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">
              Packet capture
            </p>

            <p
              className={`mt-2 text-2xl font-bold ${
                captureRunning === true
                  ? "text-green-700"
                  : captureRunning === false
                    ? "text-orange-700"
                    : "text-gray-500"
              }`}
            >
              {captureRunning === true
                ? "Active"
                : captureRunning === false
                  ? "Inactive"
                  : "Unavailable"}
            </p>

            <p className="mt-1 text-xs text-gray-500">
              Current ingestion state
            </p>
          </article>

          <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">
              Persistence worker
            </p>

            <p
              className={`mt-2 text-2xl font-bold ${
                persistenceWorkerRunning === true
                  ? "text-green-700"
                  : persistenceWorkerRunning === false
                    ? "text-orange-700"
                    : "text-gray-500"
              }`}
            >
              {persistenceWorkerRunning === true
                ? "Running"
                : persistenceWorkerRunning === false
                  ? "Stopped"
                  : "Unavailable"}
            </p>

            <p className="mt-1 text-xs text-gray-500">
              Worker process state
            </p>
          </article>
        </div>

        {backendLoading && (
          <p className="text-xs text-gray-500">
            Loading or refreshing backend metrics and alerts...
          </p>
        )}

        {captureRunning === false && (
          <p className="text-sm text-orange-800">
            Packet capture is currently inactive. Persisted historical
            records remain available, but these metrics do not demonstrate
            current traffic ingestion.
          </p>
        )}
      </section>

      {/* Telemetry-dependent widgets */}
      <HighPriorityNotifications
        events={transactions}
        isMockMode={isMockMode}
      />

      <SystemLatencyWidget
        latencyMs={latestLatencyMs}
        isMock={isMockMode}
        source={latencySource}
      />

      <AlertResponsivenessMonitor
        latestLatencyMs={displayedRenderLatency}
        measurementSource={measurementSource}
      />

      <TelemetryRenderProbe
        event={latestEvent}
        onRendered={handleEventRendered}
      />

      {/* Demo-only security controls and charts */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Demonstration Widgets
          </h2>

          <p className="text-sm text-amber-700">
            The following controls, attack stream, and charts are
            demonstration components. They are not connected to
            backend enforcement or confirmed attack activity.
          </p>
        </div>

        <EnforcementToggle />

        <BlockedAttacksLiveStream />

        <AttackDistributionChart />

        <VirtualizedIncidentList />
      </section>

      {/* API endpoint activity */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            API Endpoint Activity
          </h2>

          <p className="mt-1 text-sm text-gray-600">
            Transactions received through the telemetry client.
            Data depends on the active telemetry source.
          </p>
        </div>

        <EndpointDataTable
          transactions={transactions}
          connectionStatus={connectionStatus}
          isMockMode={isMockMode}
          loading={connectionStatus === "connecting"}
        />
      </section>

      {/* Actual persisted backend alerts */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Recent Security Alerts
          </h2>

          <p className="mt-1 text-sm text-gray-600">
            Persisted alerts retrieved from the backend.
            These are potential findings, not independently confirmed
            vulnerabilities.
          </p>

          {!backendLoading && (
            <p className="mt-1 text-xs text-gray-500">
              Showing {mergedAlerts.length} of{" "}
              {formatMetric(totalIncidentCount)} persisted alerts.
            </p>
          )}
        </div>

        {backendLoading && backendAlerts.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
            Loading backend alerts...
          </div>
        ) : (
          <IncidentAlertGrid incidents={mergedAlerts} />
        )}
      </section>
    </section>
  );
}
