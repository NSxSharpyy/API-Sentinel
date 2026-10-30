
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  ShieldAlert,
  X,
} from "lucide-react";

const HIGH_SEVERITY_VALUES = new Set([
  "high",
  "critical",
  "urgent",
  "p1",
]);

const DEMO_EVENTS = [
  {
    method: "GET",
    endpoint: "/api/v1/accounts/demo",
    severity: "high",
    title: "Simulated high-priority event",
  },
  {
    method: "POST",
    endpoint: "/api/v1/login/demo",
    severity: "critical",
    title: "Simulated critical-priority event",
  },
  {
    method: "PUT",
    endpoint: "/api/v1/users/demo",
    severity: "urgent",
    title: "Simulated urgent security event",
  },
  {
    method: "GET",
    endpoint: "/api/v1/admin/demo",
    severity: "p1",
    title: "Simulated P1 security alert",
  },
];

function getSeverity(event) {
  return String(
    event?.severity ??
      event?.severityLabel ??
      event?.risk ??
      event?.priority ??
      "",
  )
    .trim()
    .toLowerCase();
}

function getEventId(event, index) {
  return String(
    event?.id ??
      event?.eventId ??
      event?.incidentId ??
      `${event?.method ?? event?.httpMethod ?? "EVENT"}-${
        event?.endpoint ?? event?.path ?? "unknown"
      }-${index}`,
  );
}

function normalizeEvent(event, index) {
  const severity = getSeverity(event);

  return {
    id: getEventId(event, index),
    method: String(
      event?.method ?? event?.httpMethod ?? "EVENT",
    ),
    endpoint: String(
      event?.endpoint ??
        event?.path ??
        event?.url ??
        "Unknown endpoint",
    ),
    severity,
    title: String(
      event?.title ??
        event?.name ??
        (severity === "critical"
          ? "Critical security event"
          : "High-priority security event"),
    ),
  };
}

export default function HighPriorityNotifications({
  events = [],
  isMockMode = true,
}) {
  const [activeBanner, setActiveBanner] = useState(null);
  const [toast, setToast] = useState(null);
  const [demoMessage, setDemoMessage] = useState("");

  const processedIds = useRef(new Set());
  const toastTimer = useRef(null);
  const demoSequence = useRef(0);

  function clearToastTimer() {
    if (toastTimer.current !== null) {
      clearTimeout(toastTimer.current);
      toastTimer.current = null;
    }
  }

  function showNotification(event, isDemo = false) {
    clearToastTimer();

    setActiveBanner(event);
    setToast(event);

    setDemoMessage(
      isDemo
        ? "Demonstration only. This is not a real attack or a confirmed blocked request."
        : "",
    );

    toastTimer.current = setTimeout(() => {
      setToast(null);
      toastTimer.current = null;
    }, 8000);
  }

  useEffect(() => {
    if (!Array.isArray(events)) {
      return;
    }

    const highPriorityEvents = events
      .filter(
        (event) =>
          event &&
          typeof event === "object" &&
          HIGH_SEVERITY_VALUES.has(getSeverity(event)),
      )
      .map((event, index) => normalizeEvent(event, index));

    const unseenEvents = highPriorityEvents.filter(
      (event) => !processedIds.current.has(event.id),
    );

    if (unseenEvents.length === 0) {
      return;
    }

    unseenEvents.forEach((event) => {
      processedIds.current.add(event.id);
    });

    const nextEvent = unseenEvents[0];

    if (toastTimer.current !== null) {
      clearTimeout(toastTimer.current);
      toastTimer.current = null;
    }

    setActiveBanner(nextEvent);
    setToast(nextEvent);
    setDemoMessage("");

    toastTimer.current = setTimeout(() => {
      setToast(null);
      toastTimer.current = null;
    }, 8000);
  }, [events]);

  useEffect(() => {
    return () => {
      if (toastTimer.current !== null) {
        clearTimeout(toastTimer.current);
        toastTimer.current = null;
      }
    };
  }, []);

  function showDemoNotification() {
    const eventIndex =
      demoSequence.current % DEMO_EVENTS.length;

    const selectedEvent = DEMO_EVENTS[eventIndex];

    demoSequence.current += 1;

    const demoEvent = {
      ...selectedEvent,
      id: `DEMO-HIGH-${demoSequence.current}`,
    };

    showNotification(demoEvent, true);
  }

  function dismissToast() {
    clearToastTimer();
    setToast(null);
  }

  function dismissBanner() {
    setActiveBanner(null);
  }

  return (
    <section
      className="space-y-3"
      aria-label="Security notifications"
    >
      {activeBanner && (
        <div
          role="alert"
          className="flex flex-wrap items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-950"
        >
          <ShieldAlert
            size={22}
            className="mt-0.5 shrink-0 text-red-600"
            aria-hidden="true"
          />

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold">
                High-priority security event
              </h2>

              <span className="rounded-full border border-red-300 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase">
                {activeBanner.severity}
              </span>

              {(isMockMode || demoMessage) && (
                <span className="rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900">
                  DEMO / SIMULATED
                </span>
              )}
            </div>

            <p className="mt-1 text-sm">
              {activeBanner.title}
            </p>

            <p className="mt-1 break-all text-xs text-red-800">
              {activeBanner.method} {activeBanner.endpoint}
            </p>

            {(isMockMode || demoMessage) && (
              <p className="mt-2 text-xs text-amber-900">
                {demoMessage ||
                  "Mock telemetry: this notification is not evidence of a real attack."}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={dismissBanner}
            aria-label="Dismiss high-priority banner"
            className="rounded-md p-1 text-red-700 hover:bg-red-100"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2">
          <BellRing
            size={18}
            className="text-sky-600"
            aria-hidden="true"
          />

          <div>
            <p className="text-sm font-semibold text-slate-900">
              Notification test
            </p>

            <p className="text-xs text-slate-500">
              Generate a clearly labeled sample alert.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={showDemoNotification}
          className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-semibold text-sky-800 hover:bg-sky-100"
        >
          Test notification
        </button>
      </div>

      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed right-4 top-4 z-50 w-[calc(100%-2rem)] max-w-sm rounded-xl border border-red-200 bg-white p-4 text-slate-900 shadow-xl"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              size={21}
              className="mt-0.5 shrink-0 text-red-600"
              aria-hidden="true"
            />

            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold">
                {toast.title}
              </p>

              <p className="mt-1 break-all text-xs text-slate-600">
                {toast.method} {toast.endpoint}
              </p>

              <p className="mt-2 text-[11px] text-slate-500">
                {isMockMode || demoMessage
                  ? "Simulated event — demo only"
                  : "High-priority event from the supplied telemetry"}
              </p>
            </div>

            <button
              type="button"
              onClick={dismissToast}
              aria-label="Dismiss toast notification"
              className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              <X size={17} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
