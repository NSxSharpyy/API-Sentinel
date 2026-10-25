
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { mockAttackDistribution } from "../../data/mockAttackDistribution";

export default function AttackDistributionChart() {
  return (
    <section
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
      aria-labelledby="attack-distribution-title"
    >
      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="attack-distribution-title"
            className="text-lg font-semibold text-gray-900"
          >
            Sample Attack Distribution Over Time
          </h2>

          <p className="mt-1 text-sm text-gray-500">
            Illustrative event counts by sample hourly interval.
            These values are not observed live traffic.
          </p>
        </div>

        <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
          Illustrative sample
        </span>
      </div>

      <div
        className="h-80 w-full"
        role="img"
        aria-label="Illustrative line chart of sample possible BOLA,
          authentication abuse, and rate-limit event counts.
          Values are not live security detections."
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={mockAttackDistribution}
            margin={{ top: 10, right: 15, left: 0, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" />

            <XAxis
              dataKey="time"
              tick={{ fontSize: 12 }}
              tickMargin={8}
            />

            <YAxis
              allowDecimals={false}
              width={35}
              tick={{ fontSize: 12 }}
            />

            <Tooltip
              contentStyle={{
                borderRadius: "10px",
                border: "1px solid #e5e7eb",
                fontSize: "12px",
              }}
            />

            <Legend />

            <Line
              type="monotone"
              dataKey="bola"
              name="Possible BOLA events (sample)"
              stroke="#DC2626"
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />

            <Line
              type="monotone"
              dataKey="authAbuse"
              name="Authentication abuse (sample)"
              stroke="#7C3AED"
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />

            <Line
              type="monotone"
              dataKey="rateLimit"
              name="Rate-limit events (sample)"
              stroke="#D97706"
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-3 text-xs text-gray-500">
        All values are illustrative. A real attack trend requires
        verified backend events, validated event classifications,
        and a defined time-aggregation window.
      </p>
    </section>
  );
}
