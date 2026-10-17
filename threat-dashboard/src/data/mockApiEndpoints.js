
/*
 * DAY 8 + DAY 10
 * API Attack Surface Inventory and Visual Classification
 *
 * DEMO DATA ONLY — Not connected to the backend.
 * Classifications are illustrative examples, not verified findings.
 */

export const mockApiEndpoints = [
  {
    id: 1,
    method: "GET",
    path: "/api/v1/users",
    source: "Official",
    classification: "Official",
    description: "Retrieve user records",
    lastSeen: "Documented",
  },
  {
    id: 2,
    method: "POST",
    path: "/api/v1/auth/login",
    source: "Official",
    classification: "Official",
    description: "Authenticate a user",
    lastSeen: "Documented",
  },
  {
    id: 3,
    method: "GET",
    path: "/api/v1/products",
    source: "Official",
    classification: "Official",
    description: "Retrieve product records",
    lastSeen: "Documented",
  },
  {
    id: 4,
    method: "GET",
    path: "/api/internal/debug",
    source: "Discovered",
    classification: "Shadow",
    description:
      "Observed endpoint; approval and documentation need verification",
    lastSeen: "Recently observed",
  },
  {
    id: 5,
    method: "POST",
    path: "/api/v1/reports/export",
    source: "Discovered",
    classification: "Shadow",
    description:
      "Observed endpoint; inventory status needs verification",
    lastSeen: "Recently observed",
  },
  {
    id: 6,
    method: "GET",
    path: "/legacy/api/accounts",
    source: "Discovered",
    classification: "Zombie",
    description:
      "Example of a retired or deprecated endpoint still being observed",
    lastSeen: "Recently observed",
  },
];
