
import { Shield } from "lucide-react"

export default function Dashboard() {
  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex items-center gap-3">
          <Shield className="h-8 w-8 text-gray-900" />

          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Security Dashboard
            </h1>

            <p className="text-gray-600">
              Real-time threat monitoring interface
            </p>
          </div>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <p className="text-sm text-gray-500">
              System Status
            </p>

            <p className="mt-2 text-xl font-semibold text-gray-900">
              Initializing
            </p>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <p className="text-sm text-gray-500">
              Active Threats
            </p>

            <p className="mt-2 text-xl font-semibold text-gray-900">
              0
            </p>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <p className="text-sm text-gray-500">
              Telemetry
            </p>

            <p className="mt-2 text-xl font-semibold text-gray-900">
              Waiting
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}