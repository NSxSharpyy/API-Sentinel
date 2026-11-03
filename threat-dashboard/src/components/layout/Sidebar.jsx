
import {
  Activity,
  FileCode2,
  LayoutDashboard,
  Network,
  Settings,
  ShieldAlert,
} from "lucide-react";

import { NavLink } from "react-router-dom";

const navigationItems = [
  {
    label: "Overview",
    path: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    label: "Incidents",
    path: "/incidents",
    icon: ShieldAlert,
  },
  {
    label: "API Attack Surface",
    path: "/api-surface",
    icon: Network,
  },
  {
    label: "OpenAPI Contract",
    path: "/openapi-contract",
    icon: FileCode2,
  },
  {
    label: "Settings",
    path: "/settings",
    icon: Settings,
  },
];

export default function Sidebar({ collapsed, onNavigate }) {
  return (
    <aside
      className={`${
        collapsed ? "w-[72px]" : "w-60"
      } flex h-full shrink-0 flex-col border-r border-gray-200 bg-white transition-[width,background-color,border-color] duration-200 dark:border-gray-700 dark:bg-gray-900`}
      aria-label="Main navigation"
    >
      <div className="border-b border-gray-100 p-4 dark:border-gray-800">
        <div
          className={`flex items-center gap-3 ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <Activity
            size={21}
            className="shrink-0 text-blue-600"
            aria-hidden="true"
          />

          {!collapsed && (
            <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
              Security Center
            </span>
          )}
        </div>
      </div>

      <nav
        className="flex-1 space-y-1 overflow-y-auto p-3"
        aria-label="Dashboard sections"
      >
        {navigationItems.map((item) => {
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onNavigate}
              title={collapsed ? item.label : undefined}
              aria-label={item.label}
              className={({ isActive }) =>
                `flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  collapsed ? "justify-center" : ""
                } ${
                  isActive
                    ? "bg-blue-50 font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-100"
                }`
              }
            >
              <Icon
                size={19}
                className="shrink-0"
                aria-hidden="true"
              />

              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-gray-200 p-3 dark:border-gray-700">
        {!collapsed && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Frontend scaffold · Day 2
          </p>
        )}
      </div>
    </aside>
  );
}
