
import { Menu, ShieldCheck } from "lucide-react";
import ThemeToggle from "../ui/ThemeToggle.jsx";

export default function TopNavigation({
  sidebarCollapsed,
  onToggleSidebar,
  onToggleMobileMenu,
  connectionStatus = "disconnected",
}) {
  const statusLabels = {
    connected: "Backend connected",
    connecting: "Connecting...",
    disconnected: "Backend disconnected",
    error: "Connection error",
    mock: "Mock telemetry active",
  };

  const statusColors = {
    connected: "bg-green-500",
    connecting: "bg-amber-500",
    disconnected: "bg-gray-400",
    error: "bg-red-500",
    mock: "bg-amber-500",
  };

  const statusLabel =
    statusLabels[connectionStatus] || "Unknown status";

  const statusColor =
    statusColors[connectionStatus] || "bg-gray-400";

  const handleMenuClick = () => {
    if (window.innerWidth < 768) {
      onToggleMobileMenu();
    } else {
      onToggleSidebar();
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-2 border-b border-gray-200 bg-white px-3 transition-colors sm:px-6 dark:border-gray-700 dark:bg-gray-900">
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={handleMenuClick}
          aria-label="Toggle navigation menu"
          aria-expanded={
            window.innerWidth < 768
              ? undefined
              : !sidebarCollapsed
          }
          className="shrink-0 rounded-lg p-2 text-gray-600 hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-blue-600 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          <Menu size={21} aria-hidden="true" />
        </button>

        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white">
            <ShieldCheck size={21} aria-hidden="true" />
          </div>

          <div className="min-w-0">
            <p className="truncate font-semibold text-gray-900 dark:text-gray-100">
              API Sentinel
            </p>
            <p className="hidden text-xs text-gray-500 sm:block dark:text-gray-400">
              Threat Monitoring
            </p>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        <div
          className="flex items-center gap-2 rounded-full border border-gray-200 px-2 py-2 sm:px-3 dark:border-gray-700"
          aria-label={`Backend connection status: ${statusLabel}`}
          role="status"
        >
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${statusColor}`}
            aria-hidden="true"
          />

          <span className="hidden text-xs font-medium text-gray-600 sm:inline sm:text-sm dark:text-gray-300">
            {statusLabel}
          </span>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
