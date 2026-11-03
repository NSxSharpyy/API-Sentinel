
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "api-sentinel-theme";

function getInitialTheme() {
  try {
    const savedTheme = localStorage.getItem(STORAGE_KEY);

    if (savedTheme === "dark" || savedTheme === "light") {
      return savedTheme;
    }
  } catch {
    // Continue with the default theme if storage is unavailable.
  }

  return "light";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    const isDark = theme === "dark";

    root.classList.toggle("dark", isDark);
    root.dataset.theme = theme;
    root.style.colorScheme = theme;

    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // The selected theme still works for this session.
    }
  }, [theme]);

  const isDark = theme === "dark";

  function toggleTheme() {
    setTheme((currentTheme) =>
      currentTheme === "dark" ? "light" : "dark",
    );
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      aria-pressed={isDark}
      title={`Switch to ${isDark ? "light" : "dark"} mode`}
      className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-blue-600 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
    >
      {isDark ? (
        <Sun size={18} aria-hidden="true" />
      ) : (
        <Moon size={18} aria-hidden="true" />
      )}

      <span className="hidden sm:inline">
        {isDark ? "Light mode" : "Dark mode"}
      </span>
    </button>
  );
}
