
import { useState } from "react";
import { Outlet } from "react-router-dom";
import { X } from "lucide-react";

import TopNavigation from "../components/layout/TopNavigation.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";
import SystemStatusBanner from "../components/layout/SystemStatusBanner.jsx";

export default function DashboardLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const toggleSidebar = () => {
    setSidebarCollapsed((previous) => !previous);
  };

  const toggleMobileMenu = () => {
    setMobileMenuOpen((previous) => !previous);
  };

  const closeMobileMenu = () => {
    setMobileMenuOpen(false);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <TopNavigation
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={toggleSidebar}
        onToggleMobileMenu={toggleMobileMenu}
      />

      <div className="flex min-h-[calc(100vh-64px)]">
        {/* Desktop sidebar */}
        <div className="hidden md:block">
          <Sidebar collapsed={sidebarCollapsed} />
        </div>

        {/* Mobile navigation drawer */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-black/40"
              aria-label="Close navigation menu"
              onClick={closeMobileMenu}
            />

            <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-white shadow-xl">
              <div className="flex h-16 items-center justify-between border-b border-gray-200 px-4">
                <span className="font-semibold text-gray-900">
                  Navigation
                </span>

                <button
                  type="button"
                  onClick={closeMobileMenu}
                  aria-label="Close navigation menu"
                  className="rounded-lg p-2 text-gray-600 hover:bg-gray-100"
                >
                  <X size={20} aria-hidden="true" />
                </button>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto">
                <Sidebar
                  collapsed={false}
                  onNavigate={closeMobileMenu}
                />
              </div>
            </div>
          </div>
        )}

        {/* Main viewport */}
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-[1600px] space-y-6">
            <SystemStatusBanner />
            <Outlet />
          </div>
        </main>
      </div>

      {/* Mobile menu button */}
      <div className="fixed bottom-4 right-4 z-30 md:hidden">
        <button
          type="button"
          onClick={toggleMobileMenu}
          aria-expanded={mobileMenuOpen}
          className="rounded-full bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg"
        >
          {mobileMenuOpen ? "Close menu" : "Open menu"}
        </button>
      </div>
    </div>
  );
}

