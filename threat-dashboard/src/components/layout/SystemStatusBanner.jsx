
import { Info } from "lucide-react";

export default function SystemStatusBanner() {
  return (
    <section
      role="status"
      className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4"
    >
      <Info
        size={20}
        className="mt-0.5 shrink-0 text-blue-700"
        aria-hidden="true"
      />

      <div>
        <h2 className="text-sm font-semibold text-blue-900">
          Frontend is running
        </h2>

        <p className="mt-1 text-sm text-blue-800">
          Dashboard layout is ready. Live backend telemetry
          has not been connected yet.
        </p>
      </div>
    </section>
  );
}