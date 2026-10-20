
import { useCallback, useEffect, useState } from "react";

import { createTelemetryClient } from "../services/websocketClient";
import { telemetryConfig } from "../config/telemetry";

function normalizeTransaction(message) {
  const candidate = message?.data ?? message;

  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return null;
  }

  const method =
    typeof candidate.method === "string"
      ? candidate.method.trim().toUpperCase()
      : "";

  const rawEndpoint =
    typeof candidate.endpoint === "string"
      ? candidate.endpoint
      : typeof candidate.path === "string"
        ? candidate.path
        : "";

  const endpoint = rawEndpoint.trim();

  if (!method || !endpoint) {
    return null;
  }

  const rawStatusCode =
    candidate.statusCode ?? candidate.status_code ?? null;

  const rawLatency =
    candidate.latencyMs ?? candidate.latency_ms ?? null;

  const parsedStatusCode =
    rawStatusCode === null || rawStatusCode === ""
      ? null
      : Number(rawStatusCode);

  const parsedLatency =
    rawLatency === null || rawLatency === ""
      ? null
      : Number(rawLatency);

  const timestamp =
    typeof candidate.timestamp === "string" ||
    typeof candidate.timestamp === "number"
      ? candidate.timestamp
      : new Date().toISOString();

  return {
    id:
      candidate.id ??
      `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    method,
    endpoint,
    statusCode:
      parsedStatusCode !== null &&
      Number.isFinite(parsedStatusCode)
        ? parsedStatusCode
        : null,
    latencyMs:
      parsedLatency !== null &&
      Number.isFinite(parsedLatency) &&
      parsedLatency >= 0
        ? parsedLatency
        : null,
    timestamp,
  };
}

export function useTelemetry() {
  const [connectionStatus, setConnectionStatus] =
    useState("disconnected");

  const [latestMessage, setLatestMessage] = useState(null);
  const [lastError, setLastError] = useState("");
  const [transactions, setTransactions] = useState([]);

  const dismissError = useCallback(() => {
    setLastError("");
  }, []);

  useEffect(() => {
    let active = true;

    const client = createTelemetryClient({
      onStatus: (status) => {
        if (!active) return;

        setConnectionStatus(status);

        if (status === "connected" || status === "mock") {
          setLastError("");
        }
      },

      onMessage: (message) => {
        if (!active) return;

        setLatestMessage(message);

        const transaction = normalizeTransaction(message);

        if (!transaction) {
          setLastError(
            "Received a telemetry message without a valid method or endpoint."
          );
          return;
        }

        setLastError("");

        // Add newest transactions first and retain at most 100.
        setTransactions((previous) =>
          [transaction, ...previous].slice(0, 100)
        );
      },

      onError: (message) => {
        if (!active) return;

        setLastError(
          typeof message === "string"
            ? message
            : "An unexpected telemetry error occurred."
        );
      },
    });

    client.connect();

    return () => {
      active = false;
      client.disconnect();
    };
  }, []);

  return {
    connectionStatus,
    latestMessage,
    lastError,
    isMockMode: telemetryConfig.mode === "mock",
    transactions,
    dismissError,
  };
}
