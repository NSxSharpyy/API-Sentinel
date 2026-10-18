
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

    // Avoid opening another socket while one is connecting or open.
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

      try {
        const message = JSON.parse(event.data);
        onMessage?.(message);
      } catch {
        onError?.(
          "Received a message that is not valid JSON."
        );
      }
    });

    nextSocket.addEventListener("error", () => {
      if (closed || socket !== nextSocket) return;

      onError?.("WebSocket connection error.");

      // The close event is responsible for reconnecting.
    });

    nextSocket.addEventListener("close", () => {
      if (closed || socket !== nextSocket) return;

      socket = null;
      scheduleReconnect();
    });
  }

  function connect() {
    // Prevent duplicate intervals or WebSocket connections.
    if (!closed) return;

    closed = false;
    clearReconnectTimer();

    if (telemetryConfig.mode === "mock") {
      onStatus?.("mock");

      let index = 0;

      const emitMockEvent = () => {
        if (closed) return;

        const event = mockEvents[index % mockEvents.length];

        onMessage?.({
          ...event,
          data: {
            ...event.data,
            timestamp: new Date().toISOString(),
          },
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

      // Close both CONNECTING and OPEN sockets.
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
