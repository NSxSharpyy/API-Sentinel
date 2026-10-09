
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import DashboardLayout from "../layouts/DashboardLayout";
import Dashboard from "../pages/Dashboard";

function PlaceholderPage({ title, description }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6">
      <h1 className="text-2xl font-bold text-gray-900">
        {title}
      </h1>

      <p className="mt-2 text-sm text-gray-600">
        {description}
      </p>

      <p className="mt-4 text-xs text-gray-500">
        Placeholder only — functionality is scheduled for a later day.
      </p>
    </section>
  );
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<DashboardLayout />}>
          <Route
            path="/"
            element={<Navigate to="/dashboard" replace />}
          />

          <Route
            path="/dashboard"
            element={<Dashboard />}
          />

          <Route
            path="/incidents"
            element={
              <PlaceholderPage
                title="Incidents"
                description="Incident cards and severity badges will be added on Day 3."
              />
            }
          />

          <Route
            path="/api-surface"
            element={
              <PlaceholderPage
                title="API Attack Surface"
                description="The endpoint inventory is scheduled for Day 8."
              />
            }
          />

          <Route
            path="/settings"
            element={
              <PlaceholderPage
                title="Settings"
                description="Project settings and enforcement controls will be implemented on their scheduled days."
              />
            }
          />

          <Route
            path="*"
            element={<Navigate to="/dashboard" replace />}
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}