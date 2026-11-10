import { useCallback, useEffect, useState } from "react";

import { createAlertWebSocketClient } from "../services/alertWebSocketClient";
import { telemetryConfig } from "../config/telemetry";
import { mergeAlerts } from "../utils/alerts";

export function useAlertStream() {
  const [liveAlerts, setLiveAlerts] = useState([]);
  const [alertConnectionStatus, setAlertConnectionStatus] =
    useState("disconnected");
  const [alertConnectionError, setAlertConnectionError] = useState("");

  const dismissAlertError = useCallback(() => {
    setAlertConnectionError("");
  }, []);

  useEffect(() => {
    const client = createAlertWebSocketClient({
      url: telemetryConfig.alertWebsocketUrl,

      onStatus: (status) => {
        setAlertConnectionStatus(status);

        if (status === "connected") {
          setAlertConnectionError("");
        }
      },

      onAlert: (alert) => {
        setAlertConnectionError("");

        setLiveAlerts((previous) =>
          mergeAlerts(previous, [alert]).slice(0, 100)
        );
      },

      onError: (message) => {
        setAlertConnectionError(message);
      },
    });

    client.connect();

    return () => client.disconnect();
  }, []);

  return {
    liveAlerts,
    alertConnectionStatus,
    alertConnectionError,
    dismissAlertError,
  };
}
