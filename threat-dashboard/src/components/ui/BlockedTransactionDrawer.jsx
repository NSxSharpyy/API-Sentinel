
import { useEffect } from "react";
import { X, ShieldCheck, Clock3, FileSearch } from "lucide-react";

function BlockedTransactionDrawer({ event, onClose }) {
  useEffect(() => {
    if (!event) return undefined;

    function handleKeyDown(keyEvent) {
      if (keyEvent.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [event, onClose]);

  if (!event) return null;

  const isDemo = event.status === "Simulated";

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/40"
      onMouseDown={(mouseEvent) => {
        if (mouseEvent.target === mouseEvent.currentTarget) {
          onClose();
        }
      }}
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="transaction-drawer-title"
        className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl"
      >
        <div className="sticky top-0 flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Transaction inspection
            </p>
            <h2
              id="transaction-drawer-title"
              className="mt-1 text-lg font-semibold text-slate-900"
            >
              {event.id}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close transaction inspection"
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-6 p-5">
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <div className="flex items-start gap-2">
              <ShieldCheck
                className="mt-0.5 h-5 w-5 shrink-0 text-amber-700"
                aria-hidden="true"
              />
              <div>
                <p className="font-semibold text-amber-900">
                  {isDemo ? "Demo event — not verified" : "Event details"}
                </p>
                <p className="mt-1 text-sm text-amber-900">
                  {isDemo
                    ? "This sample record does not prove that a real transaction was blocked."
                    : "Review the source and verification status before treating this record as a confirmed block."}
                </p>
              </div>
            </div>
          </div>

          <section>
            <h3 className="font-semibold text-slate-900">
              Event summary
            </h3>

            <dl className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
              <div className="grid grid-cols-[120px_1fr] gap-3 p-3">
                <dt className="text-sm text-slate-500">Event ID</dt>
                <dd className="break-all text-sm font-medium text-slate-800">
                  {event.id}
                </dd>
              </div>

              <div className="grid grid-cols-[120px_1fr] gap-3 p-3">
                <dt className="text-sm text-slate-500">Time</dt>
                <dd className="text-sm text-slate-800">{event.time}</dd>
              </div>

              <div className="grid grid-cols-[120px_1fr] gap-3 p-3">
                <dt className="text-sm text-slate-500">Endpoint</dt>
                <dd className="break-all text-sm font-medium text-slate-800">
                  <span className="mr-2 inline-block rounded bg-slate-100 px-2 py-1 text-xs">
                    {event.method}
                  </span>
                  {event.endpoint}
                </dd>
              </div>

              <div className="grid grid-cols-[120px_1fr] gap-3 p-3">
                <dt className="text-sm text-slate-500">Severity</dt>
                <dd className="text-sm font-medium text-slate-800">
                  {event.severity}
                </dd>
              </div>

              <div className="grid grid-cols-[120px_1fr] gap-3 p-3">
                <dt className="text-sm text-slate-500">Reason</dt>
                <dd className="text-sm text-slate-800">{event.reason}</dd>
              </div>

              <div className="grid grid-cols-[120px_1fr] gap-3 p-3">
                <dt className="text-sm text-slate-500">Record status</dt>
                <dd className="text-sm font-medium text-slate-800">
                  {event.status}
                </dd>
              </div>
            </dl>
          </section>

          <section>
            <div className="flex items-center gap-2">
              <FileSearch
                className="h-5 w-5 text-indigo-600"
                aria-hidden="true"
              />
              <h3 className="font-semibold text-slate-900">
                Sanitized request metadata
              </h3>
            </div>

            <p className="mt-2 text-sm text-slate-500">
              Illustrative metadata only. This is not a captured request
              payload from the backend.
            </p>

            <div className="mt-3 overflow-hidden rounded-lg border border-slate-200">
              <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2">
                <span className="text-xs font-medium text-slate-600">
                  Example metadata
                </span>
                <span className="text-xs text-emerald-700">
                  Sanitized demo
                </span>
              </div>

              <dl className="divide-y divide-slate-100 p-3">
                <div className="grid grid-cols-[120px_1fr] gap-3 py-2">
                  <dt className="text-sm text-slate-500">Content type</dt>
                  <dd className="break-all text-sm text-slate-800">
                    application/json
                  </dd>
                </div>

                <div className="grid grid-cols-[120px_1fr] gap-3 py-2">
                  <dt className="text-sm text-slate-500">Authorization</dt>
                  <dd className="text-sm font-medium text-emerald-700">
                    [REDACTED]
                  </dd>
                </div>

                <div className="grid grid-cols-[120px_1fr] gap-3 py-2">
                  <dt className="text-sm text-slate-500">Cookies</dt>
                  <dd className="text-sm font-medium text-emerald-700">
                    [REDACTED]
                  </dd>
                </div>

                <div className="grid grid-cols-[120px_1fr] gap-3 py-2">
                  <dt className="text-sm text-slate-500">Request body</dt>
                  <dd className="text-sm text-slate-600">
                    Not included in this demo
                  </dd>
                </div>
              </dl>
            </div>
          </section>

          <div className="flex items-start gap-2 rounded-lg bg-slate-50 p-3">
            <Clock3
              className="mt-0.5 h-4 w-4 shrink-0 text-slate-500"
              aria-hidden="true"
            />
            <p className="text-xs leading-5 text-slate-600">
              Production integration should use a stable event identifier,
              verified enforcement outcome, server timestamp, and a
              backend-approved sanitized payload. Never expose secrets in
              the browser.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Close inspection
          </button>
        </div>
      </aside>
    </div>
  );
}

export default BlockedTransactionDrawer;
