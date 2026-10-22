
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import DashboardLayout from "../layouts/DashboardLayout";

import Dashboard from "../pages/Dashboard";
import Incidents from "../pages/Incidents";
import ApiSurface from "../pages/ApiSurface";

import OpenApiContractViewer from "../components/ui/OpenApiContractViewer";

// Reusable placeholder page for features scheduled for later.
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
        Placeholder only - functionality is scheduled for a later day.
      </p>
    </section>
  );
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Shared layout for all application pages */}
        <Route element={<DashboardLayout />}>
          {/* Redirect the home page to the dashboard */}
          <Route
            path="/"
            element={<Navigate to="/dashboard" replace />}
          />

          {/* Dashboard */}
          <Route
            path="/dashboard"
            element={<Dashboard />}
          />

          {/* Incidents */}
          <Route
            path="/incidents"
            element={<Incidents />}
          />

          {/* API Attack Surface */}
          <Route
            path="/api-surface"
            element={<ApiSurface />}
          />

          {/* Day 13: OpenAPI Contract Viewer */}
          <Route
            path="/openapi-contract"
            element={<OpenApiContractViewer />}
          />

          {/* Settings placeholder */}
          <Route
            path="/settings"
            element={
              <PlaceholderPage
                title="Settings"
                description="Project settings and enforcement controls will be implemented on their scheduled days."
              />
            }
          />

          {/* Redirect unknown URLs to the dashboard */}
          <Route
            path="*"
            element={<Navigate to="/dashboard" replace />}
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
