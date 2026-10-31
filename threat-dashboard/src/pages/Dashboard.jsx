
import { useCallback, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { mockIncidents } from "../data/mockIncidents";
import IncidentAlertGrid from "../components/ui/IncidentAlertGrid";
import EndpointDataTable from "../components/ui/EndpointDataTable";
import AttackDistributionChart from "../components/ui/AttackDistributionChart";
import SystemLatencyWidget from "../components/ui/SystemLatencyWidget";
import AlertResponsivenessMonitor from "../components/ui/AlertResponsivenessMonitor";
import TelemetryRenderProbe from "../components/ui/TelemetryRenderProbe";
import EnforcementToggle from "../components/ui/EnforcementToggle";

export default function Dashboard() {
  const {
    transactions = [],
    connectionStatus = "disconnected",
    isMockMode = false,
    latestLatencyMs = null,
  } = useOutletContext();

  const [renderMeasurement, setRenderMeasurement] =
    useState(null);

  // Existing demo incidents, not live telemetry alerts.
  const incidents = mockIncidents;

  const criticalCount = incidents.filter(
    (incident) =>
      incident.severity?.toLowerCase() === "critical"
  ).length;

  const highCount = incidents.filter(
    (incident) =>
      incident.severity?.toLowerCase() === "high"
  ).length;

  const latencySource = isMockMode
    ? "Simulated telemetry value"
  : typeof latestLatencyMs === "number" &&
      Number.isFinite(latestLatencyMs) &&
      latestLatencyMs >= 0
    ? "Telemetry field; measurement boundary unverified"
    : "";

  // Transactions are stored newest first by useTelemetry.
  const latestEvent = transactions[0] ?? null;

  const handleEventRendered = useCallback(
    (eventId, receivedAtMs, latencyMs, source) => {
      setRenderMeasurement({
        eventId,
        receivedAtMs,
        latencyMs,
        source,
      });
    },
    []
  );

  // Only show a timing measurement matching the latest event.
  const measurementMatchesLatestEvent =
    latestEvent !== null &&
    latestEvent.receivedAtMs !== null &&
    renderMeasurement?.eventId === latestEvent.id &&
    renderMeasurement?.receivedAtMs ===
      latestEvent.receivedAtMs;

  const displayedRenderLatency =
    measurementMatchesLatestEvent
      ? renderMeasurement.latencyMs
      : null;

  const measurementSource =
    measurementMatchesLatestEvent
      ? renderMeasurement.source === "mock"
        ? "Mock telemetry: receipt-to-render measurement"
        : "Live telemetry: browser receipt-to-render measurement"
      : latestEvent
        ? "Measuring the latest telemetry event"
        : "Waiting for telemetry timing";

  return (
    <section className="space-y-6">
      {/* Dashboard Heading */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          Security Overview
        </h1>

        <p className="mt-1 text-sm text-gray-600">
          Security incident monitoring and alert summaries.
        </p>

        <p className="mt-2 text-xs font-medium text-amber-700">
          DEMO DATA — Incident alerts use temporary demo data.
          Endpoint transactions depend on telemetry availability.
        </p>
      </div>

      {/* Incident Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">
            Critical incidents
          </p>

          <p className="mt-2 text-3xl font-bold text-red-700">
            {criticalCount}
          </p>

          <p className="mt-1 text-xs text-gray-500">
            Count within the temporary demo dataset
          </p>
        </article>

        <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">
            High-severity incidents
          </p>

          <p className="mt-2 text-3xl font-bold text-orange-700">
            {highCount}
          </p>

          <p className="mt-1 text-xs text-gray-500">
            Count within the temporary demo dataset
          </p>
        </article>
      </div>

      {/* Day 15 — System Latency */}
      <SystemLatencyWidget
        latencyMs={latestLatencyMs}
        isMock={isMockMode}
        source={latencySource}
      />

      {/* Day 16 — Receipt-to-render measurement */}
      <AlertResponsivenessMonitor
        latestLatencyMs={displayedRenderLatency}
        measurementSource={measurementSource}
      />

      {/* Day 16 — Measure the rendered telemetry event */}
      <TelemetryRenderProbe
        event={latestEvent}
        onRendered={handleEventRendered}
      />

      {/* Day 17 — Global Enforcement Demo Control */}
      <EnforcementToggle />

      {/* Day 11 — Attack Distribution Over Time */}
      <AttackDistributionChart />

      {/* API Endpoint Activity */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            API Endpoint Activity
          </h2>

          <p className="mt-1 text-sm text-gray-600">
            Recent endpoint transactions received through the telemetry
            client. Data appears here when valid transactions are received.
          </p>
        </div>

        <EndpointDataTable
          transactions={transactions}
          connectionStatus={connectionStatus}
          isMockMode={isMockMode}
          loading={connectionStatus === "connecting"}
        />
      </section>

      {/* Existing Recent Security Alerts */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Recent Security Alerts
          </h2>

          <p className="mt-1 text-sm text-gray-600">
            SIMULATED DATA — These sample incidents demonstrate
            the alert interface. They are not live security detections.
          </p>
        </div>

        <IncidentAlertGrid incidents={incidents} />
      </section>
    </section>
  );
}
