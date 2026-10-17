
import { useMemo, useState } from "react";
import {
  Archive,
  Database,
  Search,
  ScanSearch,
  ShieldCheck,
  Layers3,
  Info,
} from "lucide-react";

import { mockApiEndpoints } from "../data/mockApiEndpoints";

// Classification badge: Official, Shadow, or Zombie
function ClassificationBadge({ classification }) {
  const styles = {
    Official: "bg-green-100 text-green-800 ring-green-600/20",
    Shadow: "bg-amber-100 text-amber-800 ring-amber-600/20",
    Zombie: "bg-red-100 text-red-800 ring-red-600/20",
  };

  const icons = {
    Official: ShieldCheck,
    Shadow: ScanSearch,
    Zombie: Archive,
  };

  const Icon = icons[classification] || Info;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${
        styles[classification] ||
        "bg-gray-100 text-gray-700 ring-gray-500/20"
      }`}
    >
      <Icon size={13} />
      {classification || "Unclassified"}
    </span>
  );
}

// Source badge: where the endpoint entry came from
function SourceBadge({ source }) {
  const styles = {
    Official: "bg-blue-50 text-blue-700",
    Discovered: "bg-purple-50 text-purple-700",
  };

  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${
        styles[source] || "bg-gray-100 text-gray-700"
      }`}
    >
      {source}
    </span>
  );
}

// HTTP method badge
function MethodBadge({ method }) {
  const styles = {
    GET: "bg-blue-50 text-blue-700",
    POST: "bg-green-50 text-green-700",
    PUT: "bg-amber-50 text-amber-700",
    PATCH: "bg-orange-50 text-orange-700",
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

// Reusable summary card
function SummaryCard({ title, value, description, icon: Icon }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-500">
            {title}
          </p>

          <p className="mt-2 text-3xl font-bold text-gray-900">
            {value}
          </p>

          <p className="mt-1 text-xs text-gray-500">
            {description}
          </p>
        </div>

        <div className="rounded-lg bg-gray-100 p-2.5 text-gray-700">
          <Icon size={21} />
        </div>
      </div>
    </div>
  );
}

export default function ApiSurface() {
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("All");
  const [classificationFilter, setClassificationFilter] =
    useState("All");

  // Calculate classification totals for the full inventory
  const officialCount = mockApiEndpoints.filter(
    (endpoint) => endpoint.classification === "Official"
  ).length;

  const shadowCount = mockApiEndpoints.filter(
    (endpoint) => endpoint.classification === "Shadow"
  ).length;

  const zombieCount = mockApiEndpoints.filter(
    (endpoint) => endpoint.classification === "Zombie"
  ).length;

  // Apply search, source filter, and classification filter
  const filteredEndpoints = useMemo(() => {
    const query = search.trim().toLowerCase();

    return mockApiEndpoints.filter((endpoint) => {
      const matchesSearch =
        endpoint.path.toLowerCase().includes(query) ||
        endpoint.method.toLowerCase().includes(query) ||
        endpoint.description.toLowerCase().includes(query);

      const matchesSource =
        sourceFilter === "All" ||
        endpoint.source === sourceFilter;

      const matchesClassification =
        classificationFilter === "All" ||
        endpoint.classification === classificationFilter;

      return (
        matchesSearch &&
        matchesSource &&
        matchesClassification
      );
    });
  }, [search, sourceFilter, classificationFilter]);

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <header>
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-indigo-100 p-3 text-indigo-700">
            <Layers3 size={25} />
          </div>

          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              API Attack Surface
            </h1>

            <p className="mt-1 text-sm text-gray-500">
              Inventory and visual classification of API endpoints.
            </p>
          </div>
        </div>
      </header>

      {/* Demo data warning */}
      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <Info
          className="mt-0.5 shrink-0 text-amber-700"
          size={20}
        />

        <div>
          <p className="font-semibold text-amber-900">
            Demonstration data only
          </p>

          <p className="mt-1 text-sm text-amber-800">
            Endpoint classifications are illustrative mock data,
            not verified backend findings. Confirm ownership,
            documentation, and deprecation status before classifying
            real endpoints. A discovered endpoint is not automatically
            vulnerable or a Shadow endpoint.
          </p>
        </div>
      </div>

      {/* Summary cards */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Total Endpoints"
          value={mockApiEndpoints.length}
          description="Endpoints in this demo inventory"
          icon={Database}
        />

        <SummaryCard
          title="Official"
          value={officialCount}
          description="Approved/documented examples"
          icon={ShieldCheck}
        />

        <SummaryCard
          title="Shadow"
          value={shadowCount}
          description="Inventory verification pending"
          icon={ScanSearch}
        />

        <SummaryCard
          title="Zombie"
          value={zombieCount}
          description="Retired endpoint example"
          icon={Archive}
        />
      </section>

      {/* Endpoint inventory */}
      <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-200 p-5">
          <h2 className="text-lg font-semibold text-gray-900">
            Endpoint Inventory
          </h2>

          <p className="mt-1 text-sm text-gray-500">
            Search endpoints and inspect their classifications.
          </p>

          {/* Search and filters */}
          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="relative">
              <Search
                size={18}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />

              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search path, method, or description..."
                aria-label="Search API endpoints"
                className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>

            <select
              value={sourceFilter}
              onChange={(event) =>
                setSourceFilter(event.target.value)
              }
              aria-label="Filter by source"
              className="rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            >
              <option value="All">All sources</option>
              <option value="Official">Official source</option>
              <option value="Discovered">Discovered source</option>
            </select>

            <select
              value={classificationFilter}
              onChange={(event) =>
                setClassificationFilter(event.target.value)
              }
              aria-label="Filter by classification"
              className="rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            >
              <option value="All">All classifications</option>
              <option value="Official">Official</option>
              <option value="Shadow">Shadow</option>
              <option value="Zombie">Zombie</option>
            </select>
          </div>
        </div>

        {/* Responsive endpoint table */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[850px] text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-5 py-3 font-semibold">
                  Method
                </th>

                <th className="px-5 py-3 font-semibold">
                  Endpoint Path
                </th>

                <th className="px-5 py-3 font-semibold">
                  Source
                </th>

                <th className="px-5 py-3 font-semibold">
                  Classification
                </th>

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

                  <td className="whitespace-nowrap px-5 py-4">
                    <code className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-800">
                      {endpoint.path}
                    </code>
                  </td>

                  <td className="whitespace-nowrap px-5 py-4">
                    <SourceBadge source={endpoint.source} />
                  </td>

                  <td className="whitespace-nowrap px-5 py-4">
                    <ClassificationBadge
                      classification={endpoint.classification}
                    />
                  </td>

                  <td className="max-w-xs px-5 py-4 text-gray-600">
                    {endpoint.description}
                  </td>

                  <td className="whitespace-nowrap px-5 py-4 text-gray-600">
                    {endpoint.lastSeen}
                  </td>
                </tr>
              ))}

              {filteredEndpoints.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center">
                    <Search
                      size={28}
                      className="mx-auto mb-3 text-gray-400"
                    />

                    <p className="font-medium text-gray-800">
                      No endpoints found
                    </p>

                    <p className="mt-1 text-sm text-gray-500">
                      Try another search or change your filters.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Inventory result count */}
        <div className="border-t border-gray-200 px-5 py-3 text-sm text-gray-500">
          Showing {filteredEndpoints.length} of{" "}
          {mockApiEndpoints.length} endpoints
        </div>
      </section>
    </div>
  );
}
