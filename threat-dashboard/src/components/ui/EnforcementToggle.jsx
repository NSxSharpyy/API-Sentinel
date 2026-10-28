
import { useState } from "react";
import {
  ShieldCheck,
  ShieldOff,
  AlertTriangle,
} from "lucide-react";

function EnforcementToggle() {
  // This is local demo state, not real backend enforcement.
  const [isEnabled, setIsEnabled] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);

  // Calculate the requested state without changing the current state.
  const requestedState = !isEnabled;

  function handleToggleRequest() {
    setShowConfirmation(true);
  }

  function handleCancel() {
    setShowConfirmation(false);
  }

  function handleConfirm() {
    setIsEnabled(requestedState);
    setShowConfirmation(false);
  }

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-labelledby="enforcement-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div
            className={`rounded-lg p-2.5 ${
              isEnabled ? "bg-emerald-50" : "bg-slate-100"
            }`}
          >
            {isEnabled ? (
              <ShieldCheck
                className="h-5 w-5 text-emerald-600"
                aria-hidden="true"
              />
            ) : (
              <ShieldOff
                className="h-5 w-5 text-slate-500"
                aria-hidden="true"
              />
            )}
          </div>

          <div>
            <h2
              id="enforcement-title"
              className="font-semibold text-slate-900"
            >
              Global Enforcement
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Manage the enforcement control state
            </p>
          </div>
        </div>

        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            isEnabled
              ? "bg-emerald-50 text-emerald-700"
              : "bg-slate-100 text-slate-600"
          }`}
          aria-live="polite"
        >
          {isEnabled ? "Enabled (Demo)" : "Disabled (Demo)"}
        </span>
      </div>

      <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <div className="flex items-start gap-2">
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
            aria-hidden="true"
          />

          <p className="text-sm text-amber-900">
            Demo control only. Changing this setting does not enable or
            disable real traffic blocking. Backend integration and
            authorization are required.
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-800">
            Enforcement is {isEnabled ? "enabled" : "disabled"} in this demo
          </p>

          <p className="mt-1 text-xs text-slate-500">
            No backend configuration is changed.
          </p>
        </div>

        <button
          type="button"
          onClick={handleToggleRequest}
          className={`rounded-lg px-4 py-2 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-offset-2 ${
            isEnabled
              ? "bg-rose-600 hover:bg-rose-700 focus:ring-rose-500"
              : "bg-emerald-600 hover:bg-emerald-700 focus:ring-emerald-500"
          }`}
        >
          {isEnabled ? "Request Disable" : "Request Enable"}
        </button>
      </div>

      {showConfirmation && (
        <div
          className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4"
          role="group"
          aria-label="Confirm enforcement change"
        >
          <h3 className="font-semibold text-slate-900">
            Confirm demo state change
          </h3>

          <p className="mt-2 text-sm text-slate-600">
            Change the demo state to{" "}
            <strong>
              {requestedState ? "Enabled" : "Disabled"}
            </strong>
            ? This will not change real backend enforcement.
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleConfirm}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            >
              Confirm demo change
            </button>

            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export default EnforcementToggle;
