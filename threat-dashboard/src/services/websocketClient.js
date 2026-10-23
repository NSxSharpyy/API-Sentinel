
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

  const baseDelay = 1000;
  const maxDelay = 30000;

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function scheduleReconnect() {
    if (closed || reconnectTimer !== null) return;

    const delay = Math.min(
      baseDelay * 2 ** retryAttempt,
      maxDelay
    );

    retryAttempt += 1;

    onStatus?.("reconnecting");
    onError?.(
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
    if (closed) return;

    if (!telemetryConfig.websocketUrl) {
      onStatus?.("error");
      onError?.("WebSocket URL is not configured.");
      return;
    }

    if (
      socket &&
      (socket.readyState === WebSocket.CONNECTING ||
        socket.readyState === WebSocket.OPEN)
    ) {
      return;
    }

    onStatus?.(
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
      if (closed || socket !== nextSocket) return;

      retryAttempt = 0;
      onStatus?.("connected");
    });

    nextSocket.addEventListener("message", (event) => {
      if (closed || socket !== nextSocket) return;

      // Record receipt time before parsing and React state updates.
      const receivedAtMs = performance.now();

      try {
        const message = JSON.parse(event.data);

        onMessage?.(message, {
          receivedAtMs,
          source: "live",
        });
      } catch {
        onError?.(
          "Received a message that is not valid JSON."
        );
      }
    });

    nextSocket.addEventListener("error", () => {
      if (closed || socket !== nextSocket) return;

      onError?.("WebSocket connection error.");
    });

    nextSocket.addEventListener("close", () => {
      if (closed || socket !== nextSocket) return;

      socket = null;
      scheduleReconnect();
    });
  }

  function connect() {
    if (!closed) return;

    closed = false;
    clearReconnectTimer();

    if (telemetryConfig.mode === "mock") {
      onStatus?.("mock");

      let index = 0;

      const emitMockEvent = () => {
        if (closed) return;

        const event = mockEvents[index % mockEvents.length];

        const message = {
          ...event,
          data: {
            ...event.data,
            timestamp: new Date().toISOString(),
          },
        };

        // Use the same browser clock for the timing baseline.
        const receivedAtMs = performance.now();

        onMessage?.(message, {
          receivedAtMs,
          source: "mock",
        });

        index += 1;
      };

      emitMockEvent();

      mockTimer = window.setInterval(
        emitMockEvent,
        5000
      );

      return;
    }

    openSocket();
  }

  function disconnect() {
    closed = true;

    clearReconnectTimer();

    if (mockTimer !== null) {
      window.clearInterval(mockTimer);
      mockTimer = null;
    }

    if (socket !== null) {
      const currentSocket = socket;
      socket = null;

      if (
        currentSocket.readyState === WebSocket.CONNECTING ||
        currentSocket.readyState === WebSocket.OPEN
      ) {
        currentSocket.close();
      }
    }

    retryAttempt = 0;
    onStatus?.("disconnected");
  }

  return {
    connect,
    disconnect,
  };
}
