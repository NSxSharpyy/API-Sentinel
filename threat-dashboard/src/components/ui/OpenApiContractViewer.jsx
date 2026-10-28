
import { useMemo, useState } from "react";
import {
  Braces,
  ChevronDown,
  ChevronRight,
  FileCode2,
  Info,
  ListTree,
  Search,
} from "lucide-react";

import { mockOpenApiContract } from "../../data/mockOpenApiContract";

const HTTP_METHODS = [
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "options",
  "head",
];

const METHOD_STYLES = {
  get: "bg-blue-100 text-blue-800",
  post: "bg-green-100 text-green-800",
  put: "bg-amber-100 text-amber-800",
  patch: "bg-orange-100 text-orange-800",
  delete: "bg-red-100 text-red-800",
  options: "bg-purple-100 text-purple-800",
  head: "bg-gray-200 text-gray-800",
};

function getOperations(contract) {
  return Object.entries(contract.paths || {}).flatMap(
    ([path, pathItem]) =>
      HTTP_METHODS.filter((method) => pathItem[method]).map(
        (method) => ({
          path,
          method,
          ...pathItem[method],
        })
      )
  );
}

function MethodBadge({ method }) {
  return (
    <span
      className={`inline-flex min-w-16 justify-center rounded-md px-2 py-1 text-xs font-bold uppercase ${
        METHOD_STYLES[method] || "bg-gray-100 text-gray-700"
      }`}
    >
      {method}
    </span>
  );
}

export default function OpenApiContractViewer() {
  const contract = mockOpenApiContract;

  const operations = useMemo(
    () => getOperations(contract),
    [contract]
  );

  const [search, setSearch] = useState("");
  const [selectedKey, setSelectedKey] = useState(null);
  const [showRawContract, setShowRawContract] = useState(false);

  const filteredOperations = useMemo(() => {
    const query = search.trim().toLowerCase();

    return operations.filter((operation) => {
      return (
        operation.path.toLowerCase().includes(query) ||
        operation.method.toLowerCase().includes(query) ||
        (operation.summary || "").toLowerCase().includes(query) ||
        (operation.description || "").toLowerCase().includes(query)
      );
    });
  }, [operations, search]);

  const selectedOperation =
    filteredOperations.find(
      (operation) =>
        `${operation.method}:${operation.path}` === selectedKey
    ) ||
    filteredOperations[0] ||
    null;

  const selectedPathItem = selectedOperation
    ? contract.paths[selectedOperation.path]
    : null;

  const parameters = [
    ...(selectedPathItem?.parameters || []),
    ...(selectedOperation?.parameters || []),
  ];

  const requestContent = selectedOperation?.requestBody?.content || {};

  const requestSchema = Object.values(requestContent)[0]?.schema;

  const responseEntries = Object.entries(
    selectedOperation?.responses || {}
  );

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <header className="flex items-start gap-3">
        <div className="rounded-xl bg-indigo-100 p-3 text-indigo-700">
          <FileCode2 size={25} />
        </div>

        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            OpenAPI Contract Viewer
          </h1>

          <p className="mt-1 text-sm text-gray-500">
            Inspect documented API operations and their contract details.
          </p>
        </div>
      </header>

      {/* Sample-data warning */}
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start gap-3">
          <Info
            className="mt-0.5 shrink-0 text-amber-700"
            size={20}
          />

          <div>
            <p className="font-semibold text-amber-900">
              Sample contract — not backend-verified
            </p>

            <p className="mt-1 text-sm text-amber-800">
              This viewer uses local demonstration data. It does not
              load a discovered contract, validate live API behavior,
              or send requests to the example server.
            </p>
          </div>
        </div>
      </div>

      {/* Contract summary */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              API specification
            </p>

            <h2 className="mt-1 text-xl font-bold text-gray-900">
              {contract.info.title}
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              {contract.info.description}
            </p>
          </div>

          <span className="w-fit rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-800">
            OpenAPI {contract.openapi}
          </span>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-xs text-gray-500">Version</p>
            <p className="mt-1 font-semibold text-gray-900">
              {contract.info.version}
            </p>
          </div>

          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-xs text-gray-500">Paths</p>
            <p className="mt-1 font-semibold text-gray-900">
              {Object.keys(contract.paths || {}).length}
            </p>
          </div>

          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-xs text-gray-500">Operations</p>
            <p className="mt-1 font-semibold text-gray-900">
              {operations.length}
            </p>
          </div>
        </div>
      </section>

      {/* Operation explorer and details */}
      <section className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(280px,0.85fr)_minmax(0,1.5fr)]">
        {/* Operation list */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 p-4">
            <div className="flex items-center gap-2">
              <ListTree size={18} className="text-gray-600" />

              <h2 className="font-semibold text-gray-900">
                API Operations
              </h2>
            </div>

            <div className="relative mt-3">
              <Search
                size={17}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                aria-hidden="true"
              />

              <input
                id="openapi-operation-search"
                name="openapi-operation-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search paths or methods..."
                aria-label="Search API operations"
                autoComplete="off"
                className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
          </div>

          <div className="max-h-[500px] space-y-1 overflow-y-auto p-3">
            {filteredOperations.map((operation) => {
              const key = `${operation.method}:${operation.path}`;

              const isSelected =
                selectedOperation &&
                key ===
                  `${selectedOperation.method}:${selectedOperation.path}`;

              return (
                <button
                  type="button"
                  key={key}
                  onClick={() => setSelectedKey(key)}
                  aria-pressed={Boolean(isSelected)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    isSelected
                      ? "border-indigo-300 bg-indigo-50"
                      : "border-transparent hover:bg-gray-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <MethodBadge method={operation.method} />

                    {isSelected ? (
                      <ChevronDown size={16} />
                    ) : (
                      <ChevronRight size={16} />
                    )}
                  </div>

                  <code className="mt-2 block break-all text-xs text-gray-800">
                    {operation.path}
                  </code>

                  <p className="mt-1 text-sm text-gray-500">
                    {operation.summary || "No summary provided"}
                  </p>
                </button>
              );
            })}

            {filteredOperations.length === 0 && (
              <p className="px-3 py-8 text-center text-sm text-gray-500">
                No matching API operations.
              </p>
            )}
          </div>
        </div>

        {/* Selected operation details */}
        <div className="min-w-0 space-y-5 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          {selectedOperation ? (
            <>
              <div className="border-b border-gray-200 pb-4">
                <div className="flex flex-wrap items-center gap-2">
                  <MethodBadge method={selectedOperation.method} />

                  <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">
                    Contract operation
                  </span>
                </div>

                <h2 className="mt-3 break-all text-lg font-bold text-gray-900">
                  {selectedOperation.path}
                </h2>

                <p className="mt-1 text-sm text-gray-600">
                  {selectedOperation.summary || "No summary provided"}
                </p>

                {selectedOperation.description && (
                  <p className="mt-2 text-sm leading-6 text-gray-500">
                    {selectedOperation.description}
                  </p>
                )}
              </div>

              {/* Parameters */}
              <div>
                <h3 className="font-semibold text-gray-900">
                  Parameters
                </h3>

                {parameters.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {parameters.map((parameter, index) => (
                      <div
                        key={`${parameter.in}-${parameter.name}-${index}`}
                        className="rounded-lg border border-gray-200 p-3"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <code className="text-sm font-semibold text-gray-900">
                            {parameter.name}
                          </code>

                          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                            {parameter.in}
                          </span>

                          <span className="text-xs text-gray-500">
                            {parameter.required ? "Required" : "Optional"}
                          </span>
                        </div>

                        <p className="mt-1 text-sm text-gray-500">
                          {parameter.description ||
                            "No description provided"}
                        </p>

                        <p className="mt-1 text-xs text-gray-500">
                          Type: {parameter.schema?.type || "unspecified"}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-gray-500">
                    No parameters declared.
                  </p>
                )}
              </div>

              {/* Request body */}
              <div>
                <h3 className="font-semibold text-gray-900">
                  Request Body
                </h3>

                {selectedOperation.requestBody ? (
                  <div className="mt-2 rounded-lg border border-gray-200 p-3">
                    <p className="text-sm text-gray-700">
                      {selectedOperation.requestBody.required
                        ? "Request body required"
                        : "Request body optional"}
                    </p>

                    <p className="mt-2 text-xs text-gray-500">
                      Content type:{" "}
                      {Object.keys(requestContent).join(", ") ||
                        "Not specified"}
                    </p>

                    <pre className="mt-3 overflow-x-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
                      <code>
                        {JSON.stringify(requestSchema || {}, null, 2)}
                      </code>
                    </pre>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-gray-500">
                    No request body declared.
                  </p>
                )}
              </div>

              {/* Responses */}
              <div>
                <h3 className="font-semibold text-gray-900">
                  Responses
                </h3>

                {responseEntries.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {responseEntries.map(([status, response]) => (
                      <div
                        key={status}
                        className="flex flex-col gap-1 rounded-lg border border-gray-200 p-3 sm:flex-row sm:items-start sm:gap-3"
                      >
                        <span className="w-fit rounded-md bg-gray-100 px-2 py-1 text-xs font-bold text-gray-800">
                          {status}
                        </span>

                        <p className="text-sm text-gray-600">
                          {response.description ||
                            "No description provided"}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-gray-500">
                    No responses declared.
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="py-12 text-center">
              <Braces
                size={32}
                className="mx-auto text-gray-400"
              />

              <p className="mt-3 font-medium text-gray-800">
                No operation selected
              </p>

              <p className="mt-1 text-sm text-gray-500">
                Choose an operation or change your search.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Expandable raw specification */}
      <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <button
          type="button"
          onClick={() =>
            setShowRawContract((current) => !current)
          }
          aria-expanded={showRawContract}
          className="flex w-full items-center justify-between gap-3 p-4 text-left hover:bg-gray-50"
        >
          <span className="flex items-center gap-2 font-semibold text-gray-900">
            <Braces size={18} />
            View raw specification
          </span>

          {showRawContract ? (
            <ChevronDown size={18} />
          ) : (
            <ChevronRight size={18} />
          )}
        </button>

        {showRawContract && (
          <pre className="max-h-[500px] overflow-auto border-t border-gray-200 bg-gray-50 p-4 text-xs leading-5 text-gray-700">
            <code>{JSON.stringify(contract, null, 2)}</code>
          </pre>
        )}
      </section>
    </div>
  );
}
