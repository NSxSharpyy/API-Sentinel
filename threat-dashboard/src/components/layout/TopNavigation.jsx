
import { Menu, ShieldCheck } from "lucide-react";

export default function TopNavigation({
  sidebarCollapsed,
  onToggleSidebar,
  onToggleMobileMenu,
}) {
  const handleMenuClick = () => {
    if (window.innerWidth < 768) {
      onToggleMobileMenu();
    } else {
      onToggleSidebar();
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleMenuClick}
          aria-label="Toggle navigation menu"
          aria-expanded={
            window.innerWidth < 768
              ? undefined
              : !sidebarCollapsed
          }
          className="rounded-lg p-2 text-gray-600 hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-blue-600"
        >
          <Menu size={21} aria-hidden="true" />
        </button>

        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white">
            <ShieldCheck size={21} aria-hidden="true" />
          </div>

          <div>
            <p className="font-semibold text-gray-900">
              API Sentinel
            </p>
            <p className="hidden text-xs text-gray-500 sm:block">
              Threat Monitoring
            </p>
          </div>
        </div>
      </div>

      <div
        className="flex items-center gap-2 rounded-full border border-gray-200 px-3 py-2"
        aria-label="Backend connection status: not connected"
      >
        <span
          className="h-2 w-2 rounded-full bg-gray-400"
          aria-hidden="true"
        />

        <span className="text-xs font-medium text-gray-600 sm:text-sm">
          Backend not connected
        </span>
      </div>
    </header>
  );
}

