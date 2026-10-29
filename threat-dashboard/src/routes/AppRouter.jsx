
import { lazy, Suspense } from "react";

import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import DashboardLayout from "../layouts/DashboardLayout";

// Load page components only when their routes are needed.
const Dashboard = lazy(() => import("../pages/Dashboard"));
const Incidents = lazy(() => import("../pages/Incidents"));
const ApiSurface = lazy(() => import("../pages/ApiSurface"));

const OpenApiContractViewer = lazy(
  () => import("../components/ui/OpenApiContractViewer")
);

const RateLimitConfiguration = lazy(
  () => import("../components/ui/RateLimitConfiguration")
);

// Display a loading message while a page's JavaScript is downloaded.
function PageLoading() {
  return (
    <div
      className="flex min-h-64 items-center justify-center p-6"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm text-gray-500">
        Loading page...
      </p>
    </div>
  );
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoading />}>
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

            {/* OpenAPI Contract Viewer */}
            <Route
              path="/openapi-contract"
              element={<OpenApiContractViewer />}
            />

            {/* Rate Limiting Configuration */}
            <Route
              path="/settings"
              element={<RateLimitConfiguration />}
            />

            {/* Redirect unknown URLs to the dashboard */}
            <Route
              path="*"
              element={<Navigate to="/dashboard" replace />}
            />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
