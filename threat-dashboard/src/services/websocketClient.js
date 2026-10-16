
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
      timestamp: new Date().toISOString(),
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
      timestamp: new Date().toISOString(),
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
      timestamp: new Date().toISOString(),
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
  let closed = false;

  function connect() {
    if (socket || mockTimer !== null) {
      return;
    }

    closed = false;

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
      mockTimer = window.setInterval(emitMockEvent, 5000);

      return;
    }

    if (!telemetryConfig.websocketUrl) {
      onStatus?.("error");
      onError?.("WebSocket URL is not configured.");
      return;
    }

    onStatus?.("connecting");

    try {
      socket = new WebSocket(telemetryConfig.websocketUrl);

      socket.addEventListener("open", () => {
        if (!closed) {
          onStatus?.("connected");
        }
      });

      socket.addEventListener("message", (event) => {
        if (closed) return;

        try {
          const message = JSON.parse(event.data);
          onMessage?.(message);
        } catch {
          onError?.("Received a message that is not valid JSON.");
        }
      });

      socket.addEventListener("error", () => {
        if (!closed) {
          onStatus?.("error");
          onError?.("WebSocket connection error.");
        }
      });

      socket.addEventListener("close", () => {
        socket = null;

        if (!closed) {
          onStatus?.("disconnected");
        }
      });
    } catch {
      socket = null;
      onStatus?.("error");
      onError?.("Could not create the WebSocket connection.");
    }
  }

  function disconnect() {
    closed = true;

    if (mockTimer !== null) {
      window.clearInterval(mockTimer);
      mockTimer = null;
    }

    if (socket) {
      const currentSocket = socket;
      socket = null;

      if (currentSocket.readyState < WebSocket.CLOSING) {
        currentSocket.close();
      }
    }
  }

  return { connect, disconnect };
}
