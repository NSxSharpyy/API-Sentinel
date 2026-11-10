const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8001"
).replace(/\/+$/, "");

async function getJson(path, { signal } = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw error;
    }

    throw new Error(
      "Cannot connect to API-Sentinel backend. Check whether the backend is running.",
      { cause: error }
    );
  }

  if (!response.ok) {
    throw new Error(
      `Backend request failed: HTTP ${response.status}`
    );
  }

  try {
    return await response.json();
  } catch {
    throw new Error("Backend returned an invalid JSON response.");
  }
}

function validatePagination(limit, offset) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new RangeError("limit must be between 1 and 100.");
  }

  if (!Number.isInteger(offset) || offset < 0) {
    throw new RangeError("offset must be a non-negative integer.");
  }
}

function validateCollection(payload, resourceName) {
  if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray(payload.items) ||
    !Number.isInteger(payload.total)
  ) {
    throw new Error(
      `Invalid ${resourceName} response from backend.`
    );
  }

  return payload;
}

export async function getEndpoints({
  limit = 100,
  offset = 0,
  signal,
} = {}) {
  validatePagination(limit, offset);

  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  const payload = await getJson(
    `/api/v1/endpoints?${params}`,
    { signal }
  );

  return validateCollection(payload, "endpoints");
}

export async function getAlerts({
  limit = 100,
  offset = 0,
  severity,
  status,
  signal,
} = {}) {
  validatePagination(limit, offset);

  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  if (severity) {
    params.set("severity", severity);
  }

  if (status) {
    params.set("status", status);
  }

  const payload = await getJson(
    `/api/v1/alerts?${params}`,
    { signal }
  );

  return validateCollection(payload, "alerts");
}

export async function getMetrics({ signal } = {}) {
  const payload = await getJson(
    "/api/v1/metrics",
    { signal }
  );

  if (!payload || typeof payload !== "object") {
    throw new Error("Invalid metrics response from backend.");
  }

  return payload;
}
