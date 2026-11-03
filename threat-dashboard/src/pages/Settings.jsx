
import RateLimitConfiguration from "../components/ui/RateLimitConfiguration";
import OwaspApiSecurityMatrix from "../components/ui/OwaspApiSecurityMatrix";
import SanitizedPayloadInspector from "../components/ui/SanitizedPayloadInspector";

export default function Settings() {
  return (
    <main className="min-h-screen space-y-6 bg-slate-50 p-4 text-slate-900 sm:p-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">
          Security Settings
        </h1>

        <p className="mt-1 text-sm text-slate-500">
          Review demo rate limits, assess API security risks, and inspect
          sanitized example payloads.
        </p>
      </header>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <RateLimitConfiguration />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <OwaspApiSecurityMatrix />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <SanitizedPayloadInspector />
      </section>
    </main>
  );
}
