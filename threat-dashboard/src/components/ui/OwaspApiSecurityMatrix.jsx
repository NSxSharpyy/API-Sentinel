
import { useMemo, useState } from "react";
import {
  BookOpen,
  ExternalLink,
  Search,
  ShieldCheck,
} from "lucide-react";

import {
  OWASP_API_TOP_10,
  OWASP_REVIEW_STATUSES,
} from "../../data/owaspApiTop10";

const INITIAL_STATUS = "Not assessed";

export default function OwaspApiSecurityMatrix() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [reviewStatuses, setReviewStatuses] = useState({});

  const filteredRisks = useMemo(() => {
    const query = search.trim().toLowerCase();

    return OWASP_API_TOP_10.filter((risk) => {
      const searchableText = [
        risk.id,
        risk.name,
        risk.description,
        risk.reviewGuidance,
        ...risk.keywords,
      ]
        .join(" ")
        .toLowerCase();

      const matchesSearch =
        !query || searchableText.includes(query);

      const currentStatus =
        reviewStatuses[risk.id] ?? INITIAL_STATUS;

      const matchesStatus =
        statusFilter === "All" ||
        currentStatus === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [search, statusFilter, reviewStatuses]);

  const reviewedCount = OWASP_API_TOP_10.filter(
    (risk) => reviewStatuses[risk.id] === "Reviewed"
  ).length;

  function updateStatus(riskId, nextStatus) {
    setReviewStatuses((previous) => ({
      ...previous,
      [riskId]: nextStatus,
    }));
  }

  function clearFilters() {
    setSearch("");
    setStatusFilter("All");
  }

  return (
    <section
      className="space-y-5 rounded-xl border border-gray-200 bg-white p-4 text-gray-900 shadow-sm sm:p-6"
      aria-labelledby="owasp-matrix-title"
    >
      {/* Header */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-2">
            <ShieldCheck
              size={22}
              className="text-blue-600"
              aria-hidden="true"
            />
          </div>

          <div>
            <h2
              id="owasp-matrix-title"
              className="text-lg font-bold text-gray-900"
            >
              OWASP API Security Top 10
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              2023 risk reference and review matrix
            </p>
          </div>
        </div>

        <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700">
          {reviewedCount} of {OWASP_API_TOP_10.length} marked reviewed
        </span>
      </header>

      {/* Disclaimer */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
        <p className="text-sm font-semibold text-amber-900">
          Reference and review tracking only
        </p>

        <p className="mt-1 text-xs leading-5 text-amber-900">
          These categories do not represent confirmed vulnerabilities
          in your API. Review statuses are local UI state and are not
          saved to a backend or shared with other users.
        </p>
      </div>

      {/* Search and status filter */}
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px]">
        <label
          htmlFor="owasp-risk-search"
          className="flex min-w-0 items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100"
        >
          <Search
            size={16}
            className="shrink-0 text-gray-400"
            aria-hidden="true"
          />

          <input
            id="owasp-risk-search"
            name="owasp-risk-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search risk ID, name, or keyword..."
            className="min-w-0 flex-1 bg-transparent py-3 text-sm text-gray-900 outline-none placeholder:text-gray-400"
          />
        </label>

        <label className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
          <span className="shrink-0 text-xs text-gray-500">
            Status
          </span>

          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="min-w-0 flex-1 bg-white py-3 text-sm text-gray-900 outline-none"
          >
            <option value="All">All statuses</option>

            {OWASP_REVIEW_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Risk cards */}
      <div className="grid gap-3">
        {filteredRisks.map((risk) => {
          const currentStatus =
            reviewStatuses[risk.id] ?? INITIAL_STATUS;

          return (
            <article
              key={risk.id}
              className="rounded-lg border border-gray-200 bg-white p-4 transition-colors hover:border-gray-300"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold tracking-wide text-blue-600">
                    {risk.id}
                  </p>

                  <h3 className="mt-1 text-sm font-semibold leading-6 text-gray-900">
                    {risk.name}
                  </h3>
                </div>

                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-gray-500">
                    Local review status
                  </span>

                  <select
                    aria-label={`Review status for ${risk.id}`}
                    value={currentStatus}
                    onChange={(event) =>
                      updateStatus(risk.id, event.target.value)
                    }
                    className="max-w-full rounded-md border border-gray-300 bg-white px-2 py-2 text-xs text-gray-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  >
                    {OWASP_REVIEW_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <p className="mt-3 text-sm leading-6 text-gray-600">
                {risk.description}
              </p>

              <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3">
                <p className="text-xs font-semibold text-gray-800">
                  Suggested review focus
                </p>

                <p className="mt-1 text-xs leading-5 text-gray-600">
                  {risk.reviewGuidance}
                </p>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {risk.keywords.map((keyword) => (
                  <span
                    key={keyword}
                    className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] text-gray-600"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            </article>
          );
        })}
      </div>

      {/* Empty search results */}
      {filteredRisks.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
          <BookOpen
            size={24}
            className="mx-auto text-gray-400"
            aria-hidden="true"
          />

          <p className="mt-3 text-sm font-medium text-gray-800">
            No matching risks found
          </p>

          <p className="mt-1 text-xs text-gray-500">
            Try a different search term or review-status filter.
          </p>

          <button
            type="button"
            onClick={clearFilters}
            className="mt-3 rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-gray-200 pt-4">
        <a
          href="https://owasp.org/www-project-api-security/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          Official OWASP API Security Project
          <ExternalLink size={14} aria-hidden="true" />
        </a>

        <p className="mt-2 text-xs leading-5 text-gray-500">
          Reference: OWASP API Security Top 10, 2023 edition.
          Review statuses reset when this component is remounted
          or the page is refreshed.
        </p>
      </footer>
    </section>
  );
}
