
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom"

import Home from "../pages/Home"
import Dashboard from "../pages/Dashboard"

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />

        <Route path="/dashboard" element={<Dashboard />} />

        <Route
          path="*"
          element={<Navigate to="/dashboard" replace />}
        />
      </Routes>
    </BrowserRouter>
  )
}