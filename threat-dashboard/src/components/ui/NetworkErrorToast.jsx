
import { useEffect } from "react";
import {
  AlertTriangle,
  X,
} from "lucide-react";

export default function NetworkErrorToast({
  message,
  onDismiss,
}) {
  useEffect(() => {
    if (!message) return undefined;

    const timer = window.setTimeout(() => {
      onDismiss?.();
    }, 6000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [message, onDismiss]);

  if (!message) return null;

  return (
    <div
      role="alert"
      className="fixed right-4 top-20 z-50 flex w-[min(92vw,380px)] items-start gap-3 rounded-xl border border-red-200 bg-white p-4 shadow-lg"
    >
      <AlertTriangle
        className="mt-0.5 shrink-0 text-red-600"
        size={20}
        aria-hidden="true"
      />

      <div className="min-w-0 flex-1">
        <p className="font-semibold text-slate-900">
          Telemetry connection notice
        </p>

        <p className="mt-1 break-words text-sm text-slate-600">
          {message}
        </p>
      </div>

      <button
        type="button"
        onClick={onDismiss}
        className="rounded p-1 text-slate-500 hover:bg-slate-100"
        aria-label="Dismiss notification"
      >
        <X size={18} aria-hidden="true" />
      </button>
    </div>
  );
}
