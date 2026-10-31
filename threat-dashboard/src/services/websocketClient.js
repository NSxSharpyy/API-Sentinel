
import { telemetryConfig } from "../config/telemetry";

const mockEvents = [
  {
    type: "telemetry",
    data: {
      id: "MOCK-001",
      method: "GET",
      endpoint: "/api/v1/users",
      statusCode: 200,
      latencyMs: 42,
    },
  },
  {
    type: "telemetry",
    data: {
      id: "MOCK-002",
      method: "POST",
      endpoint: "/api/v1/auth/login",
      statusCode: 401,
      latencyMs: 86,
    },
  },
  {
    type: "telemetry",
    data: {
      id: "MOCK-003",
      method: "GET",
      endpoint: "/api/v1/orders",
      statusCode: 429,
      latencyMs: 31,
    },
  },
];

const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;
const MOCK_INTERVAL_MS = 5000;

export function createTelemetryClient({
  onMessage,
  onStatus,
  onError,
}) {
  let socket = null;
  let mockTimer = null;
  let reconnectTimer = null;
  let closed = true;
  let retryAttempt = 0;
  let socketGeneration = 0;

  function reportStatus(status) {
    onStatus?.(status);
  }

  function reportError(message) {
    onError?.(message);
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function clearMockTimer() {
    if (mockTimer !== null) {
      window.clearInterval(mockTimer);
      mockTimer = null;
    }
  }

  function scheduleReconnect() {
    if (closed || reconnectTimer !== null) {
      return;
    }

    if (!telemetryConfig.websocketUrl) {
      reportStatus("error");
      reportError("WebSocket URL is not configured.");
      return;
    }

    const delay = Math.min(
      BASE_RECONNECT_DELAY_MS * 2 ** retryAttempt,
      MAX_RECONNECT_DELAY_MS
    );

    retryAttempt += 1;

    reportStatus("reconnecting");
    reportError(
      `Connection lost. Retrying in ${Math.ceil(
        delay / 1000
      )} second(s).`
    );

    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;

      if (!closed) {
        openSocket();
      }
    }, delay);
  }

  function openSocket() {
    if (closed) {
      return;
    }

    if (!telemetryConfig.websocketUrl) {
      reportStatus("error");
      reportError("WebSocket URL is not configured.");
      return;
    }

    if (
      socket &&
      (socket.readyState === WebSocket.CONNECTING ||
        socket.readyState === WebSocket.OPEN)
    ) {
      return;
    }

    const generation = ++socketGeneration;

    reportStatus(
      retryAttempt > 0 ? "reconnecting" : "connecting"
    );

    let nextSocket;

    try {
      nextSocket = new WebSocket(
        telemetryConfig.websocketUrl
      );

      socket = nextSocket;
    } catch {
      socket = null;
      scheduleReconnect();
      return;
    }

    nextSocket.addEventListener("open", () => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) {
        return;
      }

      retryAttempt = 0;
      clearReconnectTimer();
      reportStatus("connected");
    });

    nextSocket.addEventListener("message", (event) => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) {
        return;
      }

      const receivedAtMs = performance.now();

      if (typeof event.data !== "string") {
        reportError(
          "Received a telemetry message in an unsupported format."
        );
        return;
      }

      let message;

      try {
        message = JSON.parse(event.data);
      } catch {
        reportError(
          "Received a message that is not valid JSON."
        );
        return;
      }

      try {
        onMessage?.(message, {
          receivedAtMs,
          source: "live",
        });
      } catch {
        reportError(
          "The telemetry message could not be processed."
        );
      }
    });

    nextSocket.addEventListener("error", () => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) {
        return;
      }

      reportStatus("error");
      reportError("WebSocket connection error.");
    });

    nextSocket.addEventListener("close", () => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) {
        return;
      }

      socket = null;
      scheduleReconnect();
    });
  }

  function connect() {
    if (!closed) {
      return;
    }

    closed = false;
    retryAttempt = 0;

    clearReconnectTimer();
    clearMockTimer();

    if (telemetryConfig.mode === "mock") {
      reportStatus("mock");

      let index = 0;

      function emitMockEvent() {
        if (closed) {
          return;
        }

        const event =
          mockEvents[index % mockEvents.length];

        const timestamp = new Date().toISOString();

        // IMPORTANT: The validator reads message.data,
        // so timestamp must be included inside data.
        const message = {
          ...event,
          data: {
            ...event.data,
            timestamp,
          },
          timestamp,
          metadata: {
            source: "mock",
          },
        };

        index += 1;

        try {
          onMessage?.(message, {
            receivedAtMs: performance.now(),
            source: "mock",
          });
        } catch {
          reportError(
            "The simulated telemetry event could not be processed."
          );
        }
      }

      // Emit the first event immediately.
      emitMockEvent();

      // Emit another mock event every five seconds.
      mockTimer = window.setInterval(
        emitMockEvent,
        MOCK_INTERVAL_MS
      );

      return;
    }

    openSocket();
  }

  function disconnect() {
    if (closed) {
      return;
    }

    // Prevent reconnection after an intentional shutdown.
    closed = true;
    socketGeneration += 1;

    clearReconnectTimer();
    clearMockTimer();

    const currentSocket = socket;
    socket = null;

    if (
      currentSocket &&
      (currentSocket.readyState === WebSocket.CONNECTING ||
        currentSocket.readyState === WebSocket.OPEN)
    ) {
      currentSocket.close();
    }

    retryAttempt = 0;
    reportStatus("disconnected");
  }

  return {
    connect,
    disconnect,
  };
}
