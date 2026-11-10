
export default function HttpStatusBadge({ statusCode }) {
  const code = Number(statusCode);

  let styles = "bg-slate-100 text-slate-700";

  if (Number.isFinite(code)) {
    if (code >= 200 && code < 300) {
      styles = "bg-green-100 text-green-800";
    } else if (code >= 300 && code < 400) {
      styles = "bg-blue-100 text-blue-800";
    } else if (code >= 400 && code < 500) {
      styles = "bg-amber-100 text-amber-800";
    } else if (code >= 500 && code < 600) {
      styles = "bg-red-100 text-red-800";
    }
  }

  const label = Number.isFinite(code) ? code : "Unknown";

  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${styles}`}
    >
      {label}
    </span>
  );
}
