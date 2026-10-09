
import {
  Activity,
  ShieldAlert,
  Wifi,
} from "lucide-react";

const overviewItems = [
  {
    label: "Active Threats",
    value: "—",
    description: "Awaiting telemetry integration",
    icon: ShieldAlert,
  },
  {
    label: "API Transactions",
    value: "—",
    description: "Live data not connected",
    icon: Activity,
  },
  {
    label: "Telemetry Stream",
    value: "Pending",
    description: "Backend connection not configured",
    icon: Wifi,
  },
];

export default function Dashboard() {
  return (
    <section>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          Overview
        </h1>

        <p className="mt-1 text-sm text-gray-600">
          Security monitoring dashboard
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {overviewItems.map((item) => {
          const Icon = item.icon;

          return (
            <article
              key={item.label}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-600">
                  {item.label}
                </p>

                <Icon
                  size={20}
                  className="text-gray-500"
                  aria-hidden="true"
                />
              </div>

              <p className="mt-4 text-2xl font-semibold text-gray-900">
                {item.value}
              </p>

              <p className="mt-2 text-xs text-gray-500">
                {item.description}
              </p>
            </article>
          );
        })}
      </div>

      <section className="mt-6 rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900">
          Dashboard workspace
        </h2>

        <p className="mt-2 text-sm leading-6 text-gray-600">
          This area will host the incident feed, endpoint transaction
          table, and security visualizations as those modules are
          implemented in the upcoming project days.
        </p>
      </section>
    </section>
  );
}