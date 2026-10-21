
import { useMemo, useState } from "react";
import { Search, X, ShieldAlert } from "lucide-react";
import { mockApiEndpoints } from "../data/mockApiEndpoints";

const EMPTY_ENDPOINTS = [];

const classificationOptions = [
  "All classifications",
  "Official",
  "Shadow",
  "Zombie",
];

const sourceOptions = [
  "All sources",
  "Gateway",
  "Code scan",
  "Traffic analysis",
];

const methodOptions = [
  "All methods",
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
];

function getClassificationClasses(classification) {
  switch (classification) {
    case "Official":
      return "bg-green-50 text-green-700 ring-green-600/20";
    case "Shadow":
      return "bg-amber-50 text-amber-700 ring-amber-600/20";
    case "Zombie":
      return "bg-red-50 text-red-700 ring-red-600/20";
    default:
      return "bg-gray-50 text-gray-700 ring-gray-600/20";
  }
}

function ClassificationBadge({ classification }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${getClassificationClasses(
        classification
      )}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {classification || "Unknown"}
    </span>
  );
}

function MethodBadge({ method }) {
  const colors = {
    GET: "bg-blue-50 text-blue-700",
    POST: "bg-green-50 text-green-700",
    PUT: "bg-amber-50 text-amber-700",
    PATCH: "bg-purple-50 text-purple-700",
    DELETE: "bg-red-50 text-red-700",
  };

  return (
    <span
      className={`inline-flex min-w-16 justify-center rounded-md px-2 py-1 text-xs font-bold ${
        colors[method] || "bg-gray-100 text-gray-700"
      }`}
    >
      {method || "N/A"}
    </span>
  );
}

export default function ApiSurface() {
  const [search, setSearch] = useState("");
  const [selectedSource, setSelectedSource] = useState("All sources");
  const [selectedClassification, setSelectedClassification] =
    useState("All classifications");
  const [selectedMethod, setSelectedMethod] = useState("All methods");

  const endpoints = Array.isArray(mockApiEndpoints)
    ? mockApiEndpoints
    : EMPTY_ENDPOINTS;

  const filteredEndpoints = useMemo(() => {
    const query = search.trim().toLowerCase();

    return endpoints.filter((endpoint) => {
      const endpointPath = String(
        endpoint.path ?? endpoint.endpoint ?? endpoint.url ?? ""
      );

      const endpointMethod = String(
        endpoint.method ?? ""
      ).toUpperCase();

      const endpointSource = String(
        endpoint.source ?? endpoint.discoverySource ?? ""
      );

      const endpointClassification = String(
        endpoint.classification ?? endpoint.type ?? ""
      );

      const matchesSearch =
        !query ||
        endpointPath.toLowerCase().includes(query) ||
        endpointMethod.toLowerCase().includes(query) ||
        endpointSource.toLowerCase().includes(query) ||
        endpointClassification.toLowerCase().includes(query);

      const matchesSource =
        selectedSource === "All sources" ||
        endpointSource.toLowerCase() === selectedSource.toLowerCase();

      const matchesClassification =
        selectedClassification === "All classifications" ||
        endpointClassification.toLowerCase() ===
          selectedClassification.toLowerCase();

      const matchesMethod =
        selectedMethod === "All methods" ||
        endpointMethod === selectedMethod;

      return (
        matchesSearch &&
        matchesSource &&
        matchesClassification &&
        matchesMethod
      );
    });
  }, [
    endpoints,
    search,
    selectedSource,
    selectedClassification,
    selectedMethod,
  ]);

  const clearFilters = () => {
    setSearch("");
    setSelectedSource("All sources");
    setSelectedClassification("All classifications");
    setSelectedMethod("All methods");
  };

  const hasActiveFilters =
    search.trim() !== "" ||
    selectedSource !== "All sources" ||
    selectedClassification !== "All classifications" ||
    selectedMethod !== "All methods";

  const officialCount = endpoints.filter(
    (endpoint) =>
      String(
        endpoint.classification ?? endpoint.type ?? ""
      ).toLowerCase() === "official"
  ).length;

  const shadowCount = endpoints.filter(
    (endpoint) =>
      String(
        endpoint.classification ?? endpoint.type ?? ""
      ).toLowerCase() === "shadow"
  ).length;

  const zombieCount = endpoints.filter(
    (endpoint) =>
      String(
        endpoint.classification ?? endpoint.type ?? ""
      ).toLowerCase() === "zombie"
  ).length;

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
              Discover and review API endpoints across your environment.
            </p>
          </div>
        </div>
      </header>

      <section
        aria-label="API endpoint summary"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <SummaryCard
          label="Total endpoints"
          value={endpoints.length}
        />

        <SummaryCard
          label="Official endpoints"
          value={officialCount}
        />

        <SummaryCard
          label="Shadow APIs"
          value={shadowCount}
        />

        <SummaryCard
          label="Zombie APIs"
          value={zombieCount}
        />
      </section>

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start gap-3">
          <ShieldAlert
            size={20}
            className="mt-0.5 shrink-0 text-amber-700"
            aria-hidden="true"
          />

          <div>
            <h2 className="text-sm font-semibold text-amber-900">
              Demo data — not connected to live telemetry
            </h2>

            <p className="mt-1 text-sm text-amber-800">
              These endpoints are sample data for the frontend. They do not
              represent a live API discovery scan.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Discovered endpoints
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              Search and combine filters to narrow the endpoint inventory.
            </p>
          </div>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex min-h-10 items-center justify-center gap-2 self-start rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            >
              <X size={16} aria-hidden="true" />
              Clear filters
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="relative sm:col-span-2 xl:col-span-1">
            <label
              htmlFor="api-endpoint-search"
              className="mb-1.5 block text-sm font-medium text-gray-700"
            >
              Search endpoints
            </label>

            <Search
              size={17}
              className="pointer-events-none absolute left-3 top-[42px] text-gray-400"
              aria-hidden="true"
            />

            <input
              id="api-endpoint-search"
              name="apiEndpointSearch"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search path, method..."
              autoComplete="off"
              className="min-h-10 w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </div>

          <div>
            <label
              htmlFor="api-endpoint-source"
              className="mb-1.5 block text-sm font-medium text-gray-700"
            >
              Discovery source
            </label>

            <select
              id="api-endpoint-source"
              name="apiEndpointSource"
              value={selectedSource}
              onChange={(event) => setSelectedSource(event.target.value)}
              className="min-h-10 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            >
              {sourceOptions.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="api-endpoint-classification"
              className="mb-1.5 block text-sm font-medium text-gray-700"
            >
              Classification
            </label>

            <select
              id="api-endpoint-classification"
              name="apiEndpointClassification"
              value={selectedClassification}
              onChange={(event) =>
                setSelectedClassification(event.target.value)
              }
              className="min-h-10 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            >
              {classificationOptions.map((classification) => (
                <option key={classification} value={classification}>
                  {classification}
                </option>
              ))}
            </select>
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
              name="apiEndpointMethod"
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

        <div className="flex flex-col gap-1 border-t border-gray-100 pt-4 text-sm sm:flex-row sm:items-center sm:justify-between">
          <p className="text-gray-600" aria-live="polite">
            Showing{" "}
            <span className="font-semibold text-gray-900">
              {filteredEndpoints.length}
            </span>{" "}
            of{" "}
            <span className="font-semibold text-gray-900">
              {endpoints.length}
            </span>{" "}
            endpoints
          </p>

          {hasActiveFilters && (
            <p className="text-xs text-gray-500">
              Filters are applied together.
            </p>
          )}
        </div>

        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full min-w-[760px] divide-y divide-gray-200 text-left text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th
                  scope="col"
                  className="px-4 py-3 font-semibold text-gray-600"
                >
                  Endpoint
                </th>

                <th
                  scope="col"
                  className="px-4 py-3 font-semibold text-gray-600"
                >
                  Method
                </th>

                <th
                  scope="col"
                  className="px-4 py-3 font-semibold text-gray-600"
                >
                  Source
                </th>

                <th
                  scope="col"
                  className="px-4 py-3 font-semibold text-gray-600"
                >
                  Classification
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-100 bg-white">
              {filteredEndpoints.map((endpoint, index) => {
                const path =
                  endpoint.path ??
                  endpoint.endpoint ??
                  endpoint.url ??
                  "—";

                const method = String(
                  endpoint.method ?? "N/A"
                ).toUpperCase();

                const source =
                  endpoint.source ??
                  endpoint.discoverySource ??
                  "Unknown";

                const classification =
                  endpoint.classification ??
                  endpoint.type ??
                  "Unknown";

                return (
                  <tr
                    key={`${method}-${path}-${index}`}
                    className="transition hover:bg-gray-50"
                  >
                    <td className="max-w-[420px] break-all px-4 py-3 font-mono text-xs text-gray-800 sm:text-sm">
                      {path}
                    </td>

                    <td className="px-4 py-3">
                      <MethodBadge method={method} />
                    </td>

                    <td className="px-4 py-3 text-gray-600">
                      {source}
                    </td>

                    <td className="px-4 py-3">
                      <ClassificationBadge
                        classification={classification}
                      />
                    </td>
                  </tr>
                );
              })}

              {filteredEndpoints.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center">
                    <div className="mx-auto flex max-w-sm flex-col items-center">
                      <Search
                        size={24}
                        className="mb-3 text-gray-400"
                        aria-hidden="true"
                      />

                      <p className="font-medium text-gray-900">
                        No endpoints found
                      </p>

                      <p className="mt-1 text-sm text-gray-500">
                        Try changing your search or clearing the filters.
                      </p>

                      {hasActiveFilters && (
                        <button
                          type="button"
                          onClick={clearFilters}
                          className="mt-4 rounded-lg px-3 py-2 text-sm font-semibold text-indigo-600 hover:bg-indigo-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        >
                          Clear all filters
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function SummaryCard({ label, value }) {
  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-gray-500">
        {label}
      </p>

      <p className="mt-2 text-2xl font-bold tracking-tight text-gray-900">
        {value}
      </p>
    </article>
  );
}
