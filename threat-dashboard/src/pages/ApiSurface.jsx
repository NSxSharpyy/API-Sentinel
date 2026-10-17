
import { useMemo, useState } from "react";
import {
  Search,
  ShieldCheck,
  ScanSearch,
  Layers3,
  Database,
} from "lucide-react";

import { mockApiEndpoints } from "../data/mockApiEndpoints";

function SourceBadge({ source }) {
  const isOfficial = source === "Official";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${
        isOfficial
          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
          : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
      }`}
    >
      {isOfficial ? "Official" : "Discovered"}
    </span>
  );
}

function MethodBadge({ method }) {
  const styles = {
    GET: "bg-blue-50 text-blue-700",
    POST: "bg-green-50 text-green-700",
    PUT: "bg-amber-50 text-amber-700",
    PATCH: "bg-purple-50 text-purple-700",
    DELETE: "bg-red-50 text-red-700",
  };

  return (
    <span
      className={`inline-flex min-w-16 justify-center rounded-md px-2 py-1 text-xs font-bold ${
        styles[method] || "bg-gray-100 text-gray-700"
      }`}
    >
      {method}
    </span>
  );
}

function SummaryCard({ title, value, description, icon: Icon }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-500">
            {title}
          </p>

          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900">
            {value}
          </p>

          <p className="mt-1 text-xs text-gray-500">
            {description}
          </p>
        </div>

        <div className="rounded-lg bg-indigo-50 p-3 text-indigo-600">
          <Icon size={21} />
        </div>
      </div>
    </div>
  );
}

export default function ApiSurface() {
  const [activeFilter, setActiveFilter] = useState("All");
  const [searchTerm, setSearchTerm] = useState("");

  const officialCount = mockApiEndpoints.filter(
    (endpoint) => endpoint.source === "Official"
  ).length;

  const discoveredCount = mockApiEndpoints.filter(
    (endpoint) => endpoint.source === "Discovered"
  ).length;

  const filteredEndpoints = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    return mockApiEndpoints.filter((endpoint) => {
      const matchesSource =
        activeFilter === "All" ||
        endpoint.source === activeFilter;

      const matchesSearch =
        !query ||
        endpoint.path.toLowerCase().includes(query) ||
        endpoint.method.toLowerCase().includes(query) ||
        endpoint.description.toLowerCase().includes(query);

      return matchesSource && matchesSearch;
    });
  }, [activeFilter, searchTerm]);

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Layers3 className="text-indigo-600" size={25} />

            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              API Attack Surface
            </h1>
          </div>

          <p className="mt-2 max-w-2xl text-sm text-gray-500">
            Review documented endpoints and endpoints discovered
            through observed API activity.
          </p>
        </div>

        <span className="inline-flex w-fit items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          <Database size={15} />
          Demo data
        </span>
      </div>

      {/* Mock data notice */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm font-semibold text-amber-900">
          Demonstration inventory — not connected to the backend
        </p>

        <p className="mt-1 text-sm text-amber-800">
          The endpoints below are sample data for UI development.
          A discovered endpoint is not automatically a vulnerability.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <SummaryCard
          title="Total Endpoints"
          value={mockApiEndpoints.length}
          description="All sample inventory entries"
          icon={Layers3}
        />

        <SummaryCard
          title="Official Endpoints"
          value={officialCount}
          description="Listed in the sample documented inventory"
          icon={ShieldCheck}
        />

        <SummaryCard
          title="Discovered Endpoints"
          value={discoveredCount}
          description="Observed in sample activity; verification pending"
          icon={ScanSearch}
        />
      </div>

      {/* Endpoint inventory */}
      <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-200 p-5">
          <h2 className="text-lg font-semibold text-gray-900">
            Endpoint Inventory
          </h2>

          <p className="mt-1 text-sm text-gray-500">
            Compare endpoint sources and review their paths.
          </p>

          {/* Search */}
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-gray-300 px-3 py-2 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
            <Search
              size={18}
              className="shrink-0 text-gray-400"
            />

            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search endpoint, method, or description..."
              aria-label="Search API endpoints"
              className="w-full bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-400"
            />
          </div>

          {/* Source filters */}
          <div className="mt-4 flex flex-wrap gap-2">
            {["All", "Official", "Discovered"].map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setActiveFilter(filter)}
                aria-pressed={activeFilter === filter}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                  activeFilter === filter
                    ? "bg-indigo-600 text-white"
                    : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {filter}
                {filter === "All" &&
                  ` (${mockApiEndpoints.length})`}
                {filter === "Official" &&
                  ` (${officialCount})`}
                {filter === "Discovered" &&
                  ` (${discoveredCount})`}
              </button>
            ))}
          </div>
        </div>

        {/* Responsive table */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Method</th>
                <th className="px-5 py-3 font-semibold">
                  Endpoint Path
                </th>
                <th className="px-5 py-3 font-semibold">Source</th>
                <th className="px-5 py-3 font-semibold">
                  Description
                </th>
                <th className="px-5 py-3 font-semibold">
                  Inventory Status
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-100">
              {filteredEndpoints.map((endpoint) => (
                <tr
                  key={endpoint.id}
                  className="transition hover:bg-gray-50"
                >
                  <td className="whitespace-nowrap px-5 py-4">
                    <MethodBadge method={endpoint.method} />
                  </td>

                  <td className="whitespace-nowrap px-5 py-4 font-mono text-xs font-medium text-gray-800">
                    {endpoint.path}
                  </td>

                  <td className="whitespace-nowrap px-5 py-4">
                    <SourceBadge source={endpoint.source} />
                  </td>

                  <td className="max-w-xs px-5 py-4 text-gray-600">
                    {endpoint.description}
                  </td>

                  <td className="whitespace-nowrap px-5 py-4 text-gray-500">
                    {endpoint.lastSeen}
                  </td>
                </tr>
              ))}

              {filteredEndpoints.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-5 py-12 text-center text-sm text-gray-500"
                  >
                    No endpoints match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="border-t border-gray-200 px-5 py-3 text-xs text-gray-500">
          Showing {filteredEndpoints.length} of{" "}
          {mockApiEndpoints.length} sample endpoints
        </div>
      </section>
    </div>
  );
}
