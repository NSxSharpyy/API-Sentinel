
const mode = import.meta.env.VITE_TELEMETRY_MODE || "mock";

const websocketUrl =
  import.meta.env.VITE_TELEMETRY_WS_URL || "";

export const telemetryConfig = {
  mode,
  websocketUrl,
};
