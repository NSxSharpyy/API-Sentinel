
import { useEffect, useState } from "react";
import { createTelemetryClient } from "../services/websocketClient";
import { telemetryConfig } from "../config/telemetry";

function normalizeTransaction(message) {
  const candidate = message?.data ?? message;

  if (!candidate || typeof candidate !== "object") {
    return null;
  }

  const method =
    typeof candidate.method === "string"
      ? candidate.method.toUpperCase()
      : "";

  const endpoint =
    typeof candidate.endpoint === "string"
      ? candidate.endpoint
      : typeof candidate.path === "string"
        ? candidate.path
        : "";

  if (!method || !endpoint) {
    return null;
  }

  return {
    id:
      candidate.id ??
      `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    method,
    endpoint,
    statusCode:
      candidate.statusCode ??
      candidate.status_code ??
      null,
    latencyMs:
      candidate.latencyMs ??
      candidate.latency_ms ??
      null,
    timestamp:
      candidate.timestamp ??
      new Date().toISOString(),
  };
}

export function useTelemetry() {
  const [connectionStatus, setConnectionStatus] =
    useState("disconnected");

  const [latestMessage, setLatestMessage] = useState(null);
  const [lastError, setLastError] = useState("");
  const [transactions, setTransactions] = useState([]);

  useEffect(() => {
    const client = createTelemetryClient({
      onStatus: (status) => {
        setConnectionStatus(status);

        if (
          status === "connecting" ||
          status === "connected" ||
          status === "mock"
        ) {
          setLastError("");
        }
      },

      onMessage: (message) => {
        setLatestMessage(message);

        const transaction = normalizeTransaction(message);

        if (!transaction) {
          setLastError(
            "Received a telemetry message without a valid method or endpoint."
          );
          return;
        }

        setLastError("");

        // Newest transaction first; retain at most 100 records.
        setTransactions((previous) =>
          [transaction, ...previous].slice(0, 100)
        );
      },

      onError: (message) => {
        setLastError(message);
      },
    });

    client.connect();

    return () => {
      client.disconnect();
    };
  }, []);

  return {
    connectionStatus,
    latestMessage,
    lastError,
    isMockMode: telemetryConfig.mode === "mock",
    transactions,
  };
}
