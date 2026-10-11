
import { useEffect, useState } from "react";
import { createTelemetryClient } from "../services/websocketClient";
import { telemetryConfig } from "../config/telemetry";

export function useTelemetry() {
  const [connectionStatus, setConnectionStatus] =
    useState("disconnected");

  const [latestMessage, setLatestMessage] = useState(null);
  const [lastError, setLastError] = useState("");

  useEffect(() => {
    const client = createTelemetryClient({
      onStatus: (status) => {
        setConnectionStatus(status);

        if (status !== "error") {
          setLastError("");
        }
      },

      onMessage: (message) => {
        console.log("Telemetry message received:", message);
        setLatestMessage(message);
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
  };
}
