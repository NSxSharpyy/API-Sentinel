const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

function validateAlert(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  if (
    !Number.isSafeInteger(value.incident_id) ||
    value.incident_id <= 0 ||
    typeof value.detected_at !== "string" ||
    !Number.isFinite(Date.parse(value.detected_at)) ||
    typeof value.severity !== "string" ||
    !value.severity.trim() ||
    typeof value.title !== "string" ||
    !value.title.trim() ||
    typeof value.status !== "string" ||
    !value.status.trim()
  ) {
    return null;
  }

  return {
    incident_id: value.incident_id,
    detected_at: value.detected_at,
    severity: value.severity,
    title: value.title,
    description:
      typeof value.description === "string" ? value.description : null,
    source_ip:
      typeof value.source_ip === "string" ? value.source_ip : null,
    transaction_id:
      Number.isSafeInteger(value.transaction_id) ? value.transaction_id : null,
    endpoint_id:
      Number.isSafeInteger(value.endpoint_id) ? value.endpoint_id : null,
    status: value.status,
  };
}

export function createAlertWebSocketClient({
  url,
  onAlert,
  onStatus,
  onError,
}) {
  let socket = null;
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

  function scheduleReconnect() {
    if (closed || reconnectTimer !== null) return;

    if (!url) {
      reportStatus("error");
      reportError("Alert WebSocket URL is not configured.");
      return;
    }

    const delay = Math.min(
      BASE_RECONNECT_DELAY_MS * 2 ** retryAttempt,
      MAX_RECONNECT_DELAY_MS
    );

    retryAttempt += 1;
    reportStatus("reconnecting");
    reportError(
      `Alert connection lost. Retrying in ${Math.ceil(delay / 1000)} second(s).`
    );

    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      if (!closed) openSocket();
    }, delay);
  }

  function openSocket() {
    if (closed) return;

    if (!url) {
      reportStatus("error");
      reportError("Alert WebSocket URL is not configured.");
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

    reportStatus(retryAttempt > 0 ? "reconnecting" : "connecting");

    let nextSocket;

    try {
      nextSocket = new WebSocket(url);
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
      ) return;

      retryAttempt = 0;
      clearReconnectTimer();
      reportStatus("connected");
    });

    nextSocket.addEventListener("message", (event) => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) return;

      if (typeof event.data !== "string") {
        reportError("Received an unsupported alert message format.");
        return;
      }

      let payload;

      try {
        payload = JSON.parse(event.data);
      } catch {
        reportError("Received an invalid JSON alert message.");
        return;
      }

      const alert = validateAlert(payload);

      if (!alert) {
        reportError("Received an alert that does not match the backend schema.");
        return;
      }

      try {
        onAlert?.(alert);
      } catch {
        reportError("The incoming alert could not be processed.");
      }
    });

    nextSocket.addEventListener("error", () => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) return;

      reportStatus("error");
      reportError("Alert WebSocket connection error.");
    });

    nextSocket.addEventListener("close", () => {
      if (
        closed ||
        socket !== nextSocket ||
        generation !== socketGeneration
      ) return;

      socket = null;
      scheduleReconnect();
    });
  }

  function connect() {
    if (!closed) return;

    closed = false;
    retryAttempt = 0;
    clearReconnectTimer();
    openSocket();
  }

  function disconnect() {
    if (closed) return;

    closed = true;
    socketGeneration += 1;
    clearReconnectTimer();

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

  return { connect, disconnect };
}
