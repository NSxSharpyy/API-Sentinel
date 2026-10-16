
import HttpStatusBadge from "./HttpStatusBadge";

function formatLatency(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const latency = Number(value);

  if (!Number.isFinite(latency) || latency < 0) {
    return "—";
  }

  return `${latency.toFixed(1)} ms`;
}

function formatTimestamp(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleTimeString();
}

function MethodBadge({ method }) {
  const normalized = String(method || "UNKNOWN").toUpperCase();

  const colors = {
    GET: "bg-blue-100 text-blue-800",
    POST: "bg-green-100 text-green-800",
    PUT: "bg-amber-100 text-amber-800",
    PATCH: "bg-purple-100 text-purple-800",
    DELETE: "bg-red-100 text-red-800",
  };

  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${
        colors[normalized] || "bg-slate-100 text-slate-700"
      }`}
    >
      {normalized}
    </span>
  );
}

export default function EndpointDataTable({
  transactions = [],
  loading = false,
}) {
  const rows = Array.isArray(transactions) ? transactions : [];

  return (
    <section className="mt-6 rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            API Transactions
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Recent HTTP requests received by the telemetry client
          </p>
        </div>

        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600">
          {rows.length}{" "}
          {rows.length === 1 ? "transaction" : "transactions"}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 font-semibold">HTTP Method</th>
              <th className="px-5 py-3 font-semibold">Endpoint Path</th>
              <th className="px-5 py-3 font-semibold">
                HTTP Status Code
              </th>
              <th className="px-5 py-3 font-semibold">
                Round-Trip Latency
              </th>
              <th className="px-5 py-3 font-semibold">Received At</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-5 py-10 text-center text-slate-500"
                >
                  Loading transactions...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-5 py-10 text-center text-slate-500"
                >
                  No API transactions received yet.
                </td>
              </tr>
            ) : (
              rows.map((transaction, index) => (
                <tr
                  key={`${transaction.id ?? "transaction"}-${index}`}
                  className="hover:bg-slate-50"
                >
                  <td className="px-5 py-4">
                    <MethodBadge method={transaction.method} />
                  </td>

                  <td className="max-w-sm break-all px-5 py-4 font-mono text-xs text-slate-700">
                    {transaction.endpoint || "—"}
                  </td>

                  <td className="px-5 py-4">
                    <HttpStatusBadge
                      statusCode={transaction.statusCode}
                    />
                  </td>

                  <td className="whitespace-nowrap px-5 py-4 text-slate-700">
                    {formatLatency(transaction.latencyMs)}
                  </td>

                  <td className="whitespace-nowrap px-5 py-4 text-slate-500">
                    {formatTimestamp(transaction.timestamp)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
