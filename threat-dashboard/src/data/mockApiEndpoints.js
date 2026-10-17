
/*
 * DAY 8 — API Attack Surface Inventory
 * MOCK DATA ONLY — Not connected to the backend.
 */

export const mockApiEndpoints = [
  {
    id: 1,
    method: "GET",
    path: "/api/v1/users",
    source: "Official",
    description: "Retrieve user records",
    lastSeen: "Documented",
  },
  {
    id: 2,
    method: "POST",
    path: "/api/v1/auth/login",
    source: "Official",
    description: "Authenticate a user",
    lastSeen: "Documented",
  },
  {
    id: 3,
    method: "GET",
    path: "/api/v1/products",
    source: "Official",
    description: "Retrieve product records",
    lastSeen: "Documented",
  },
  {
    id: 4,
    method: "GET",
    path: "/api/internal/debug",
    source: "Discovered",
    description: "Observed endpoint; documentation not verified",
    lastSeen: "Recently observed",
  },
  {
    id: 5,
    method: "POST",
    path: "/api/v1/reports/export",
    source: "Discovered",
    description: "Observed endpoint; documentation not verified",
    lastSeen: "Recently observed",
  },
  {
    id: 6,
    method: "GET",
    path: "/legacy/api/accounts",
    source: "Discovered",
    description: "Observed legacy endpoint; ownership unverified",
    lastSeen: "Recently observed",
  },
];
