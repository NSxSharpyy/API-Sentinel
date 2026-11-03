
export const OWASP_API_TOP_10 = [
  {
    id: "API1:2023",
    name: "Broken Object Level Authorization",
    description:
      "Review whether users can access only the individual objects they are authorized to access.",
    reviewGuidance:
      "Review object-level authorization checks and the results of authorized access-control tests.",
    keywords: ["BOLA", "IDOR", "object", "authorization", "access control"],
  },
  {
    id: "API2:2023",
    name: "Broken Authentication",
    description:
      "Review how the API verifies user identity and handles authentication credentials and sessions.",
    reviewGuidance:
      "Review authentication configuration, session handling, and relevant test evidence.",
    keywords: ["login", "authentication", "token", "session", "identity"],
  },
  {
    id: "API3:2023",
    name: "Broken Object Property Level Authorization",
    description:
      "Review whether API responses and updates expose or accept properties that a user should not access.",
    reviewGuidance:
      "Review property-level permissions, response fields, and input validation.",
    keywords: ["property", "data exposure", "mass assignment", "fields"],
  },
  {
    id: "API4:2023",
    name: "Unrestricted Resource Consumption",
    description:
      "Review controls that limit excessive use of compute, memory, bandwidth, and paid external services.",
    reviewGuidance:
      "Review request limits, pagination, payload sizes, timeouts, and resource quotas.",
    keywords: ["rate limit", "resource", "quota", "denial of service"],
  },
  {
    id: "API5:2023",
    name: "Broken Function Level Authorization",
    description:
      "Review whether users can invoke API functions that are outside their permitted roles.",
    reviewGuidance:
      "Review role and permission checks for sensitive functions and administrative actions.",
    keywords: ["function", "role", "admin", "permission", "authorization"],
  },
  {
    id: "API6:2023",
    name: "Unrestricted Access to Sensitive Business Flows",
    description:
      "Review protections for important business processes that could be abused through excessive automation.",
    reviewGuidance:
      "Review business-flow safeguards, abuse monitoring, and appropriate anti-automation controls.",
    keywords: ["business flow", "automation", "abuse", "transactions"],
  },
  {
    id: "API7:2023",
    name: "Server Side Request Forgery",
    description:
      "Review server-side features that retrieve remote resources based on supplied addresses or URLs.",
    reviewGuidance:
      "Review outbound request validation, destination restrictions, and network boundaries.",
    keywords: ["SSRF", "remote request", "URL", "network"],
  },
  {
    id: "API8:2023",
    name: "Security Misconfiguration",
    description:
      "Review API and infrastructure settings that could weaken security when configured incorrectly.",
    reviewGuidance:
      "Review security headers, CORS rules, default settings, error handling, and deployment configuration.",
    keywords: ["configuration", "CORS", "headers", "defaults", "deployment"],
  },
  {
    id: "API9:2023",
    name: "Improper Inventory Management",
    description:
      "Review whether deployed APIs, versions, and endpoints are inventoried and maintained appropriately.",
    reviewGuidance:
      "Compare the documented API inventory with approved, deployed endpoints and version records.",
    keywords: ["inventory", "shadow API", "zombie API", "version", "endpoint"],
  },
  {
    id: "API10:2023",
    name: "Unsafe Consumption of APIs",
    description:
      "Review how the application validates and handles data received from third-party or upstream APIs.",
    reviewGuidance:
      "Review upstream trust boundaries, response validation, and error handling.",
    keywords: ["third party", "upstream", "external API", "validation"],
  },
];

export const OWASP_REVIEW_STATUSES = [
  "Not assessed",
  "Under review",
  "Reviewed",
];
