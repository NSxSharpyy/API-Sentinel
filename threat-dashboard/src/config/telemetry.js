const mode =
  import.meta.env.VITE_TELEMETRY_MODE || "mock";

const websocketUrl =
  import.meta.env.VITE_TELEMETRY_WS_URL || "";

const alertWebsocketUrl =
  import.meta.env.VITE_ALERTS_WS_URL || "";

export const telemetryConfig = {
  mode,
  websocketUrl,
  alertWebsocketUrl,
};
