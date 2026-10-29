
import { useMemo, useState } from "react";
import { Gauge, Save, ShieldAlert } from "lucide-react";

const initialRules = [
  {
    id: "RL-DEMO-001",
    endpoint: "/api/v1/auth/login",
    method: "POST",
    maxRequests: 10,
    windowSeconds: 60,
    enabled: true,
  },
  {
    id: "RL-DEMO-002",
    endpoint: "/api/v1/users",
    method: "GET",
    maxRequests: 100,
    windowSeconds: 60,
    enabled: true,
  },
  {
    id: "RL-DEMO-003",
    endpoint: "/api/v1/reports/export",
    method: "POST",
    maxRequests: 5,
    windowSeconds: 60,
    enabled: false,
  },
];

const endpointOptions = [
  { method: "POST", endpoint: "/api/v1/auth/login" },
  { method: "GET", endpoint: "/api/v1/users" },
  { method: "POST", endpoint: "/api/v1/reports/export" },
  { method: "GET", endpoint: "/api/v1/products" },
];

export default function RateLimitConfiguration() {
  const [rules, setRules] = useState(initialRules);
  const [endpoint, setEndpoint] = useState("/api/v1/auth/login");
  const [maxRequests, setMaxRequests] = useState("10");
  const [windowSeconds, setWindowSeconds] = useState("60");
  const [enabled, setEnabled] = useState(true);
  const [message, setMessage] = useState("");

  const currentRule = useMemo(
    () => rules.find((rule) => rule.endpoint === endpoint),
    [rules, endpoint]
  );

  function loadEndpoint(nextEndpoint) {
    setEndpoint(nextEndpoint);

    const existing = rules.find(
      (rule) => rule.endpoint === nextEndpoint
    );

    if (existing) {
      setMaxRequests(String(existing.maxRequests));
      setWindowSeconds(String(existing.windowSeconds));
      setEnabled(existing.enabled);
    } else {
      setMaxRequests("100");
      setWindowSeconds("60");
      setEnabled(true);
    }

    setMessage("");
  }

  function handleSave(event) {
    event.preventDefault();
    setMessage("");

    const requestLimit = Number(maxRequests);
    const windowDuration = Number(windowSeconds);

    if (
      maxRequests.trim() === "" ||
      !Number.isInteger(requestLimit) ||
      requestLimit < 1 ||
      requestLimit > 100000
    ) {
      setMessage(
        "Enter a whole-number request limit between 1 and 100000."
      );
      return;
    }

    if (
      windowSeconds.trim() === "" ||
      !Number.isInteger(windowDuration) ||
      windowDuration < 1 ||
      windowDuration > 86400
    ) {
      setMessage(
        "Enter a whole-number time window between 1 and 86400 seconds."
      );
      return;
    }

    const selectedEndpoint = endpointOptions.find(
      (option) => option.endpoint === endpoint
    );

    if (!selectedEndpoint) {
      setMessage("Select a valid endpoint.");
      return;
    }

    const nextRule = {
      id: currentRule?.id ?? `RL-DEMO-${Date.now()}`,
      endpoint,
      method: selectedEndpoint.method,
      maxRequests: requestLimit,
      windowSeconds: windowDuration,
      enabled,
    };

    setRules((previousRules) => {
      const exists = previousRules.some(
        (rule) => rule.endpoint === endpoint
      );

      if (exists) {
        return previousRules.map((rule) =>
          rule.endpoint === endpoint ? nextRule : rule
        );
      }

      return [...previousRules, nextRule];
    });

    setMessage(
      "Demo configuration saved locally. No backend rate limit was changed."
    );
  }

  function toggleRule(ruleToUpdate) {
    const updatedEnabled = !ruleToUpdate.enabled;

    setRules((previousRules) =>
      previousRules.map((rule) =>
        rule.endpoint === ruleToUpdate.endpoint
          ? { ...rule, enabled: updatedEnabled }
          : rule
      )
    );

    if (ruleToUpdate.endpoint === endpoint) {
      setEnabled(updatedEnabled);
    }

    setMessage(
      "Demo rule state updated locally. Backend enforcement is unchanged."
    );
  }

  const isSuccess =
    message.startsWith("Demo configuration saved") ||
    message.startsWith("Demo rule state updated");

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-labelledby="rate-limit-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-50 p-2.5">
            <Gauge
              className="h-5 w-5 text-indigo-600"
              aria-hidden="true"
            />
          </div>

          <div>
            <h1
              id="rate-limit-title"
              className="text-xl font-semibold text-slate-900"
            >
              Rate Limiting Configuration
            </h1>

            <p className="mt-1 text-sm text-slate-500">
              Review and edit example endpoint limits.
            </p>
          </div>
        </div>

        <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
          UI-ONLY DEMO
        </span>
      </div>

      <div className="mt-5 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <ShieldAlert
          className="mt-0.5 h-5 w-5 shrink-0 text-amber-700"
          aria-hidden="true"
        />

        <p className="text-sm leading-5 text-amber-900">
          These settings are held in browser memory only. Saving or
          toggling a rule does not configure a server, persist after
          a page reload, or enforce rate limits on real traffic.
        </p>
      </div>

      <form onSubmit={handleSave} className="mt-6 space-y-4">
        <div>
          <label
            htmlFor="rate-limit-endpoint"
            className="mb-1.5 block text-sm font-medium text-slate-700"
          >
            API endpoint
          </label>

          <select
            id="rate-limit-endpoint"
            value={endpoint}
            onChange={(event) => loadEndpoint(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {endpointOptions.map((option) => (
              <option
                key={option.endpoint}
                value={option.endpoint}
              >
                {option.method} {option.endpoint}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="rate-limit-requests"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              Maximum requests
            </label>

            <input
              id="rate-limit-requests"
              type="number"
              min="1"
              max="100000"
              step="1"
              required
              value={maxRequests}
              onChange={(event) =>
                setMaxRequests(event.target.value)
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />

            <p className="mt-1 text-xs text-slate-500">
              Allowed range: 1-100000
            </p>
          </div>

          <div>
            <label
              htmlFor="rate-limit-window"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              Time window (seconds)
            </label>

            <input
              id="rate-limit-window"
              type="number"
              min="1"
              max="86400"
              step="1"
              required
              value={windowSeconds}
              onChange={(event) =>
                setWindowSeconds(event.target.value)
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />

            <p className="mt-1 text-xs text-slate-500">
              Allowed range: 1-86400
            </p>
          </div>
        </div>

        <label
          htmlFor="rate-limit-enabled"
          className="flex items-center gap-3 rounded-lg border border-slate-200 p-3"
        >
          <input
            id="rate-limit-enabled"
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            className="h-4 w-4 accent-indigo-600"
          />

          <span>
            <span className="block text-sm font-medium text-slate-800">
              Enable this demo rule
            </span>

            <span className="mt-0.5 block text-xs text-slate-500">
              Changes only the local UI state.
            </span>
          </span>
        </label>

        <button
          type="submit"
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          <Save className="h-4 w-4" aria-hidden="true" />
          Save demo configuration
        </button>

        {message && (
          <p
            role="status"
            aria-live="polite"
            className={`rounded-lg p-3 text-sm ${
              isSuccess
                ? "bg-emerald-50 text-emerald-800"
                : "bg-rose-50 text-rose-800"
            }`}
          >
            {message}
          </p>
        )}
      </form>

      <div className="mt-8">
        <h2 className="font-semibold text-slate-900">
          Configured demo rules
        </h2>

        <p className="mt-1 text-sm text-slate-500">
          Example values currently held in this component's state.
        </p>

        <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-3 py-3 font-medium">
                  Endpoint
                </th>
                <th scope="col" className="px-3 py-3 font-medium">
                  Limit
                </th>
                <th scope="col" className="px-3 py-3 font-medium">
                  Rule state
                </th>
                <th scope="col" className="px-3 py-3 font-medium">
                  Action
                </th>
              </tr>
            </thead>

            <tbody>
              {rules.map((rule) => (
                <tr
                  key={rule.id}
                  className="border-t border-slate-100"
                >
                  <td className="px-3 py-3">
                    <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                      {rule.method}
                    </span>

                    <span className="font-medium text-slate-800">
                      {rule.endpoint}
                    </span>
                  </td>

                  <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                    {rule.maxRequests} / {rule.windowSeconds}s
                  </td>

                  <td className="px-3 py-3">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        rule.enabled
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {rule.enabled
                        ? "Enabled (Demo)"
                        : "Disabled (Demo)"}
                    </span>
                  </td>

                  <td className="px-3 py-3">
                    <button
                      type="button"
                      onClick={() => toggleRule(rule)}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                    >
                      {rule.enabled ? "Disable demo" : "Enable demo"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
