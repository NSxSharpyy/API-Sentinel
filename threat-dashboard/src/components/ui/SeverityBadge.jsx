
const severityStyles = {
  Critical: "border-red-200 bg-red-50 text-red-800",
  High: "border-orange-200 bg-orange-50 text-orange-800",
  Medium: "border-amber-200 bg-amber-50 text-amber-800",
  Low: "border-green-200 bg-green-50 text-green-800",
};

export default function SeverityBadge({ severity }) {
  const normalizedSeverity =
    typeof severity === "string"
      ? severity.toLowerCase()
      : "";

  const supportedSeverities = {
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low",
  };

  const safeSeverity =
    supportedSeverities[normalizedSeverity];

  if (!safeSeverity) {
    return (
      <span className="inline-flex rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-semibold text-gray-700">
        UNKNOWN
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
        severityStyles[safeSeverity]
      }`}
    >
      {safeSeverity.toUpperCase()}
    </span>
  );
}
