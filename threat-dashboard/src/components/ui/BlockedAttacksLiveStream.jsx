
import { useMemo, useState } from "react";
import { Activity, ShieldCheck, Filter } from "lucide-react";

const demoBlockedEvents = [
  {
    id: "DEMO-BLK-001",
    time: "10:42:18",
    method: "GET",
    endpoint: "/api/v1/accounts/1042",
    severity: "High",
    reason: "Authorization policy demo",
    status: "Simulated",
  },
  {
    id: "DEMO-BLK-002",
    time: "10:41:52",
    method: "POST",
    endpoint: "/api/v1/auth/login",
    severity: "Medium",
    reason: "Rate limit demo",
    status: "Simulated",
  },
  {
    id: "DEMO-BLK-003",
    time: "10:40:31",
    method: "GET",
    endpoint: "/api/internal/debug",
    severity: "High",
    reason: "Policy match demo",
    status: "Simulated",
  },
  {
    id: "DEMO-BLK-004",
    time: "10:39:07",
    method: "POST",
    endpoint: "/api/v1/reports/export",
    severity: "Low",
    reason: "Rule evaluation demo",
    status: "Simulated",
  },
];

function BlockedAttacksLiveStream() {
  const [severityFilter, setSeverityFilter] = useState("All");

  const filteredEvents = useMemo(() => {
    if (severityFilter === "All") {
      return demoBlockedEvents;
    }

    return demoBlockedEvents.filter(
      (event) => event.severity === severityFilter,
    );
  }, [severityFilter]);

  const totalSampleEvents = demoBlockedEvents.length;

  const highSeverityCount = demoBlockedEvents.filter(
    (event) => event.severity === "High",
  ).length;

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-labelledby="blocked-stream-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-50 p-2.5">
            <ShieldCheck
              className="h-5 w-5 text-indigo-600"
              aria-hidden="true"
            />
          </div>

          <div>
            <h2
              id="blocked-stream-title"
              className="font-semibold text-slate-900"
            >
              Blocked Attacks &amp; Event Stream
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Example enforcement events for UI review
            </p>
          </div>
        </div>

        <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
          DEMO DATA
        </span>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 p-4">
          <p className="text-sm text-slate-500">
            Sample blocked-event records
          </p>
          <p className="mt-2 text-3xl font-bold text-slate-900">
            {totalSampleEvents}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Static examples, not confirmed backend blocks
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 p-4">
          <p className="text-sm text-slate-500">
            High-severity sample records
          </p>
          <p className="mt-2 text-3xl font-bold text-slate-900">
            {highSeverityCount}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Severity labels are illustrative
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity
            className="h-4 w-4 text-slate-500"
            aria-hidden="true"
          />
          <h3 className="font-semibold text-slate-800">
            Event records
          </h3>
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-600">
          <Filter className="h-4 w-4" aria-hidden="true" />
          <span>Severity</span>
          <select
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="All">All</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </label>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <th scope="col" className="px-3 py-3 font-medium">
                Time
              </th>
              <th scope="col" className="px-3 py-3 font-medium">
                Endpoint
              </th>
              <th scope="col" className="px-3 py-3 font-medium">
                Severity
              </th>
              <th scope="col" className="px-3 py-3 font-medium">
                Reason
              </th>
              <th scope="col" className="px-3 py-3 font-medium">
                Record status
              </th>
            </tr>
          </thead>

          <tbody>
            {filteredEvents.map((event) => (
              <tr
                key={event.id}
                className="border-b border-slate-100 last:border-0"
              >
                <td className="whitespace-nowrap px-3 py-3 text-slate-500">
                  {event.time}
                </td>

                <td className="px-3 py-3">
                  <div className="font-medium text-slate-800">
                    <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                      {event.method}
                    </span>
                    {event.endpoint}
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {event.id}
                  </p>
                </td>

                <td className="px-3 py-3">
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      event.severity === "High"
                        ? "bg-rose-50 text-rose-700"
                        : event.severity === "Medium"
                          ? "bg-amber-50 text-amber-800"
                          : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {event.severity}
                  </span>
                </td>

                <td className="px-3 py-3 text-slate-600">
                  {event.reason}
                </td>

                <td className="px-3 py-3">
                  <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">
                    {event.status}
                  </span>
                </td>
              </tr>
            ))}

            {filteredEvents.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-slate-500"
                >
                  No sample records match this severity.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs leading-5 text-slate-500">
        These records are hardcoded UI examples. They are not live events,
        verified attacks, or proof that the backend blocked traffic.
        Connect a confirmed enforcement-event feed before presenting
        operational blocked-attack metrics.
      </p>
    </section>
  );
}

export default BlockedAttacksLiveStream;
