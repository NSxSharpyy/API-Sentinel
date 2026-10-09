
import {
  Activity,
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
      } flex h-full shrink-0 flex-col border-r border-gray-200 bg-white transition-[width] duration-200`}
      aria-label="Main navigation"
    >
      <div className="border-b border-gray-100 p-4">
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
            <span className="text-sm font-semibold text-gray-700">
              Security Center
            </span>
          )}
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-3">
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
                    ? "bg-blue-50 font-semibold text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
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

      <div className="border-t border-gray-200 p-3">
        {!collapsed && (
          <p className="text-xs text-gray-500">
            Frontend scaffold · Day 2
          </p>
        )}
      </div>
    </aside>
  );
}