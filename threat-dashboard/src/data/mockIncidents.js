
export const mockIncidents = [
  {
    id: "INC-001",
    title: "Possible Broken Object Level Authorization",
    severity: "Critical",
    attackType: "BOLA",
    endpoint: "/api/v1/users/1042",
    method: "GET",
    statusCode: 403,
    timestamp: "2026-10-10T14:32:00Z",
    description:
      "Simulated authorization anomaly involving access to a user resource.",
  },
  {
    id: "INC-002",
    title: "Repeated Authentication Failures",
    severity: "High",
    attackType: "Authentication",
    endpoint: "/api/v1/auth/login",
    method: "POST",
    statusCode: 401,
    timestamp: "2026-10-10T14:28:00Z",
    description:
      "Simulated burst of failed authentication requests.",
  },
  {
    id: "INC-003",
    title: "Unexpected API Access Pattern",
    severity: "Medium",
    attackType: "API Abuse",
    endpoint: "/api/v1/orders",
    method: "GET",
    statusCode: 429,
    timestamp: "2026-10-10T14:20:00Z",
    description:
      "Simulated request pattern exceeding an illustrative threshold.",
  },
  {
    id: "INC-004",
    title: "Unusual Endpoint Discovery",
    severity: "Low",
    attackType: "Reconnaissance",
    endpoint: "/api/v1/catalog",
    method: "GET",
    statusCode: 200,
    timestamp: "2026-10-10T14:12:00Z",
    description:
      "Simulated low-priority event for demonstrating the alert interface.",
  },
];
