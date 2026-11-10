import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { createTelemetryClient } from "../services/websocketClient";
import { telemetryConfig } from "../config/telemetry";

const HTTP_METHODS = new Set([
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS",
  "TRACE",
  "CONNECT",
]);

function getTelemetryPayload(message) {
  if (
    !message ||
    typeof message !== "object" ||
    Array.isArray(message)
  ) {
    return null;
  }

  const candidate = message.data ?? message;

  if (
    !candidate ||
    typeof candidate !== "object" ||
    Array.isArray(candidate)
  ) {
    return null;
  }

  return candidate;
}

function parseStatusCode(value) {
  if (
    typeof value !== "number" &&
    !(typeof value === "string" && value.trim() !== "")
  ) {
    return null;
  }

  const statusCode = Number(value);

  if (
    !Number.isInteger(statusCode) ||
    statusCode < 100 ||
    statusCode > 599
  ) {
    return null;
  }

  return statusCode;
}

function parseLatency(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (
    typeof value !== "number" &&
    typeof value !== "string"
  ) {
    return null;
  }

  const latency = Number(value);

  if (!Number.isFinite(latency) || latency < 0) {
    return null;
  }

  return latency;
}

function parseTimestamp(value) {
  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }

  const timestampMs = Date.parse(value);

  if (!Number.isFinite(timestampMs)) {
    return null;
  }

  return new Date(timestampMs).toISOString();
}

function normalizeTransaction(message, generatedId) {
  const candidate = getTelemetryPayload(message);

  if (!candidate) {
    return {
      transaction: null,
      error: "Telemetry message must contain an object payload.",
    };
  }

  /*
   * Actual API-Sentinel backend format:
   * {
   *   message_type: "completed_transaction",
   *   request: { message_type, method, uri, captured_at },
   *   response: { message_type, status_code, captured_at }
   * }
   */
  if (candidate.message_type === "completed_transaction") {
    const request = candidate.request;
    const response = candidate.response;

    if (
      !request ||
      typeof request !== "object" ||
      Array.isArray(request) ||
      !response ||
      typeof response !== "object" ||
      Array.isArray(response)
    ) {
      return {
        transaction: null,
        error: "Completed transaction is missing its request or response.",
      };
    }

    if (
      request.message_type !== "request" ||
      response.message_type !== "response"
    ) {
      return {
        transaction: null,
        error: "Completed transaction contains invalid message types.",
      };
    }

    if (typeof request.method !== "string") {
      return {
        transaction: null,
        error: "Backend transaction is missing its HTTP method.",
      };
    }

    const method = request.method.trim().toUpperCase();

    if (!HTTP_METHODS.has(method)) {
      return {
        transaction: null,
        error: "Backend transaction contains an unsupported HTTP method.",
      };
    }

    if (
      typeof request.uri !== "string" ||
      request.uri.trim() === ""
    ) {
      return {
        transaction: null,
        error: "Backend transaction is missing its endpoint path.",
      };
    }

    const statusCode = parseStatusCode(response.status_code);

    if (statusCode === null) {
      return {
        transaction: null,
        error: "Backend transaction contains an invalid HTTP status code.",
      };
    }

    // Prefer response capture time; request time is a fallback.
    const timestamp =
      parseTimestamp(response.captured_at) ||
      parseTimestamp(request.captured_at);

    if (timestamp === null) {
      return {
        transaction: null,
        error: "Backend transaction has no valid capture timestamp.",
      };
    }

    return {
      transaction: {
        // The backend message has no unique transaction ID.
        // This is a local reference for the current browser session.
        id: generatedId,
        method,
        endpoint: request.uri.trim(),
        statusCode,
        // The backend WS contract does not report round-trip latency.
        latencyMs: null,
        timestamp,
      },
      error: null,
    };
  }

  /*
   * Legacy flat format used by the mock telemetry client.
   * Keep this supported so mock mode remains usable for UI demonstrations.
   */
  const rawId =
    candidate.id ??
    candidate.eventId ??
    candidate.event_id;

  const id =
    (typeof rawId === "string" || typeof rawId === "number") &&
    String(rawId).trim() !== ""
      ? String(rawId)
      : generatedId;

  if (typeof candidate.method !== "string") {
    return {
      transaction: null,
      error: "Telemetry event is missing a valid HTTP method.",
    };
  }

  const method = candidate.method.trim().toUpperCase();

  if (!HTTP_METHODS.has(method)) {
    return {
      transaction: null,
      error: "Telemetry event contains an unsupported HTTP method.",
    };
  }

  const rawEndpoint = candidate.endpoint ?? candidate.path;

  if (
    typeof rawEndpoint !== "string" ||
    rawEndpoint.trim() === ""
  ) {
    return {
      transaction: null,
      error: "Telemetry event is missing a valid endpoint.",
    };
  }

  const statusCode = parseStatusCode(
    candidate.statusCode ?? candidate.status_code
  );

  if (statusCode === null) {
    return {
      transaction: null,
      error: "Telemetry event contains a missing or invalid HTTP status code.",
    };
  }

  const latencyMs = parseLatency(
    candidate.latencyMs ?? candidate.latency_ms
  );

  const timestamp = parseTimestamp(
    candidate.timestamp ?? candidate.timestampUtc
  );

  if (timestamp === null) {
    return {
      transaction: null,
      error: "Telemetry event contains a missing or invalid timestamp.",
    };
  }

  return {
    transaction: {
      id,
      method,
      endpoint: rawEndpoint.trim(),
      statusCode,
      latencyMs,
      timestamp,
    },
    error: null,
  };
}

export function useTelemetry() {
  const [connectionStatus, setConnectionStatus] =
    useState("disconnected");

  const [latestMessage, setLatestMessage] = useState(null);
  const [latestLatencyMs, setLatestLatencyMs] = useState(null);
  const [connectionError, setConnectionError] = useState("");
  const [messageError, setMessageError] = useState("");
  const [transactions, setTransactions] = useState([]);

  const eventSequence = useRef(0);

  const dismissError = useCallback(() => {
    setConnectionError("");
    setMessageError("");
  }, []);

  useEffect(() => {
    let active = true;
    let currentStatus = "disconnected";

    const client = createTelemetryClient({
      onStatus: (status) => {
        currentStatus = status;

        if (!active) {
          return;
        }

        setConnectionStatus(status);

        if (status === "connected" || status === "mock") {
          setConnectionError("");
        }
      },

      onMessage: (message, metadata = {}) => {
        if (!active) {
          return;
        }

        eventSequence.current += 1;

        const generatedId =
          `CLIENT-${String(eventSequence.current).padStart(6, "0")}`;

        const result = normalizeTransaction(message, generatedId);

        if (!result.transaction) {
          setMessageError(result.error);
          return;
        }

        const transaction = result.transaction;

        const receivedAtMs =
          typeof metadata.receivedAtMs === "number" &&
          Number.isFinite(metadata.receivedAtMs)
            ? metadata.receivedAtMs
            : null;

        const telemetrySource =
          metadata.source === "mock" ? "mock" : "live";

        const timedTransaction = {
          ...transaction,
          receivedAtMs,
          telemetrySource,
        };

        setLatestMessage(message);
        setLatestLatencyMs(transaction.latencyMs);
        setMessageError("");

        setTransactions((previous) => {
          const isDuplicate = previous.some(
            (item) =>
              item.id === timedTransaction.id &&
              item.timestamp === timedTransaction.timestamp
          );

          if (isDuplicate) {
            return previous;
          }

          return [timedTransaction, ...previous].slice(0, 100);
        });
      },

      onError: (message) => {
        if (!active) {
          return;
        }

        const safeMessage =
          typeof message === "string"
            ? message
            : "An unexpected telemetry error occurred.";

        if (
          currentStatus === "connecting" ||
          currentStatus === "reconnecting" ||
          currentStatus === "error"
        ) {
          setConnectionError(safeMessage);
        } else {
          setMessageError(safeMessage);
        }
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
    latestLatencyMs,
    lastError: connectionError || messageError,
    isMockMode: telemetryConfig.mode === "mock",
    transactions,
    dismissError,
  };
}
