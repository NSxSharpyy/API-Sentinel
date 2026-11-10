import { useEffect, useMemo, useState } from "react";
import {
  Search,
  X,
  ShieldAlert,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { getEndpoints } from "../services/apiClient";

const PAGE_SIZE = 100;

const methodOptions = [
  "All methods",
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS",
];

function getMethod(endpoint) {
  return String(endpoint?.method ?? "Unknown").toUpperCase();
}

function formatTimestamp(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function MethodBadge({ method }) {
  const colors = {
    GET: "bg-blue-50 text-blue-700",
    POST: "bg-green-50 text-green-700",
    PUT: "bg-amber-50 text-amber-700",
    PATCH: "bg-purple-50 text-purple-700",
    DELETE: "bg-red-50 text-red-700",
  };

  const normalized = getMethod({ method });

  return (
    <span
      className={`inline-flex min-w-16 justify-center rounded-md px-2 py-1 text-xs font-bold ${
        colors[normalized] || "bg-gray-100 text-gray-700"
      }`}
    >
      {normalized}
    </span>
  );
}

function SummaryCard({ label, value }) {
  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{label}</p>

      <p className="mt-2 text-2xl font-bold tracking-tight text-gray-900">
        {value}
      </p>
    </article>
  );
}

export default function ApiSurface() {
  const [endpoints, setEndpoints] = useState([]);
  const [total, setTotal] = useState(0);

  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [selectedMethod, setSelectedMethod] =
    useState("All methods");

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    async function loadEndpoints() {
      setLoading(true);
      setError("");

      try {
        const result = await getEndpoints({
          limit: PAGE_SIZE,
          offset,
          signal: controller.signal,
        });

        if (!active) return;

        setEndpoints(result.items);
        setTotal(result.total);
      } catch (err) {
        if (!active || err?.name === "AbortError") {
          return;
        }

        setEndpoints([]);
        setTotal(0);
        setError(
          err?.message || "Unable to load discovered endpoints."
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadEndpoints();

    return () => {
      active = false;
      controller.abort();
    };
  }, [offset, reloadKey]);

  const filteredEndpoints = useMemo(() => {
    const query = search.trim().toLowerCase();

    return endpoints.filter((endpoint) => {
      const path = String(endpoint?.path ?? "");
      const host = String(endpoint?.host ?? "");
      const method = getMethod(endpoint);

      const matchesSearch =
        !query ||
        path.toLowerCase().includes(query) ||
        host.toLowerCase().includes(query) ||
        method.toLowerCase().includes(query);

      const matchesMethod =
        selectedMethod === "All methods" ||
        method === selectedMethod;

      return matchesSearch && matchesMethod;
    });
  }, [endpoints, search, selectedMethod]);

  const distinctMethods = useMemo(
    () => new Set(endpoints.map(getMethod)).size,
    [endpoints]
  );

  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const hasPreviousPage = offset > 0;
  const hasNextPage = offset + PAGE_SIZE < total;

  function clearFilters() {
    setSearch("");
    setSelectedMethod("All methods");
  }

  function refreshEndpoints() {
    setReloadKey((previous) => previous + 1);
  }

  return (
    <main className="space-y-6 p-4 sm:p-6 lg:p-8">
      <header>
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-indigo-50 p-3 text-indigo-600">
            <ShieldAlert size={24} aria-hidden="true" />
          </div>

          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              API Attack Surface
            </h1>

            <p className="mt-1 text-sm text-gray-500">
              Discovered API endpoints reported by the API-Sentinel backend.
            </p>
          </div>
        </div>
      </header>

      <section
        aria-label="API endpoint summary"
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
      >
        <SummaryCard
          label="Total discovered endpoints"
          value={loading ? "…" : total}
        />

        <SummaryCard
          label="Records on current page"
          value={loading ? "…" : endpoints.length}
        />

        <SummaryCard
          label="HTTP methods represented"
          value={loading ? "…" : distinctMethods}
        />
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Discovered endpoints
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              Live records retrieved from the backend REST API.
            </p>
          </div>

          <button
            type="button"
            onClick={refreshEndpoints}
            disabled={loading}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label
              htmlFor="api-endpoint-search"
              className="mb-1.5 block text-sm font-medium text-gray-700"
            >
              Search current page
            </label>

            <div className="relative">
              <Search
                size={17}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                aria-hidden="true"
              />

              <input
                id="api-endpoint-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search host, path, method..."
                className="min-h-10 w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm text-gray-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="api-endpoint-method"
              className="mb-1.5 block text-sm font-medium text-gray-700"
            >
              HTTP method
            </label>

            <select
              id="api-endpoint-method"
              value={selectedMethod}
              onChange={(event) => setSelectedMethod(event.target.value)}
              className="min-h-10 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            >
              {methodOptions.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </div>
        </div>

        {(search.trim() || selectedMethod !== "All methods") && (
          <button
            type="button"
            onClick={clearFilters}
            className="mt-3 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-indigo-600 hover:bg-indigo-50"
          >
            <X size={15} aria-hidden="true" />
            Clear filters
          </button>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-4 text-sm">
          <p className="text-gray-600" aria-live="polite">
            Showing{" "}
            <span className="font-semibold text-gray-900">
              {filteredEndpoints.length}
            </span>{" "}
            matching records on this page.
          </p>

          <p className="text-xs text-gray-500">
            Search and method filters apply to the current page.
          </p>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4"
          >
            <p className="text-sm font-semibold text-red-800">
              Unable to load endpoints
            </p>

            <p className="mt-1 text-sm text-red-700">{error}</p>

            <button
              type="button"
              onClick={refreshEndpoints}
              className="mt-3 rounded-lg bg-red-700 px-3 py-2 text-sm font-semibold text-white hover:bg-red-800"
            >
              Try again
            </button>
          </div>
        )}

        {!error && (
          <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full min-w-[850px] divide-y divide-gray-200 text-left text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["Host", "Endpoint path", "Method", "First seen", "Last seen"].map(
                    (heading) => (
                      <th
                        key={heading}
                        scope="col"
                        className="px-4 py-3 font-semibold text-gray-600"
                      >
                        {heading}
                      </th>
                    )
                  )}
                </tr>
              </thead>

              <tbody className="divide-y divide-gray-100 bg-white">
                {loading ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-12 text-center text-gray-500"
                    >
                      Loading discovered endpoints...
                    </td>
                  </tr>
                ) : filteredEndpoints.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-12 text-center text-gray-500"
                    >
                      {endpoints.length === 0
                        ? "No discovered endpoints returned by the backend."
                        : "No endpoints match your current filters."}
                    </td>
                  </tr>
                ) : (
                  filteredEndpoints.map((endpoint) => (
                    <tr
                      key={endpoint.id}
                      className="transition hover:bg-gray-50"
                    >
                      <td className="max-w-[180px] break-all px-4 py-3 text-gray-600">
                        {endpoint.host || "Unknown"}
                      </td>

                      <td className="max-w-[360px] break-all px-4 py-3 font-mono text-xs text-gray-800 sm:text-sm">
                        {endpoint.path || "—"}
                      </td>

                      <td className="px-4 py-3">
                        <MethodBadge method={endpoint.method} />
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-xs text-gray-600">
                        {formatTimestamp(endpoint.first_seen)}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-xs text-gray-600">
                        {formatTimestamp(endpoint.last_seen)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {!error && total > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-gray-500">
              Page {pageNumber} of {totalPages} · {total} total endpoints
            </p>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={loading || !hasPreviousPage}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft size={16} aria-hidden="true" />
                Previous
              </button>

              <button
                type="button"
                disabled={loading || !hasNextPage}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
