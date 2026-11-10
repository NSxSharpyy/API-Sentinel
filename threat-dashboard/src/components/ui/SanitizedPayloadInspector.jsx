
import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Eye,
  FileJson,
  ShieldAlert,
} from "lucide-react";

const DEMO_PAYLOAD = {
  eventId: "DEMO-PII-001",
  source: "Synthetic API response",
  user: {
    userId: "DEMO-USER-1042",
    name: "Example User",
    email: "sample.user@example.test",
    phone: "+1-202-555-0148",
    dateOfBirth: "1998-04-12",
  },
  authentication: {
    authorization: "Bearer DEMO_TOKEN_NOT_VALID",
    apiKey: "DEMO_API_KEY_NOT_VALID",
    sessionCookie: "DEMO_SESSION_NOT_VALID",
  },
  payment: {
    cardNumber: "4111111111111111",
    cvv: "123",
    currency: "USD",
  },
  request: {
    method: "GET",
    endpoint: "/api/v1/users/DEMO-USER-1042",
    status: "Simulated",
  },
};

const SENSITIVE_KEY_PATTERN =
  /password|passwd|secret|token|authorization|cookie|api.?key|credential|cvv|cvc|card.?number|account.?number|date.?of.?birth|dob|email|phone|mobile|address|passport|national.?id|aadhaar|ssn/i;

function redactString(value) {
  let result = value;
  let redactions = 0;

  const patterns = [
    {
      regex: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
      replacement: "[REDACTED_EMAIL]",
    },
    {
      regex: /\b(?:\+?\d[\d ()-]{7,}\d)\b/g,
      replacement: "[REDACTED_PHONE_OR_NUMBER]",
    },
  ];

  for (const pattern of patterns) {
    result = result.replace(pattern.regex, () => {
      redactions += 1;
      return pattern.replacement;
    });
  }

  return {
    value: result,
    redactions,
  };
}

function sanitizeValue(value, key = "") {
  if (SENSITIVE_KEY_PATTERN.test(key)) {
    return {
      value: "[REDACTED]",
      redactions: 1,
    };
  }

  if (typeof value === "string") {
    return redactString(value);
  }

  if (Array.isArray(value)) {
    let redactions = 0;

    const sanitizedArray = value.map((item) => {
      const result = sanitizeValue(item);
      redactions += result.redactions;
      return result.value;
    });

    return {
      value: sanitizedArray,
      redactions,
    };
  }

  if (value !== null && typeof value === "object") {
    let redactions = 0;
    const sanitizedObject = {};

    for (const [childKey, childValue] of Object.entries(value)) {
      const result = sanitizeValue(childValue, childKey);

      sanitizedObject[childKey] = result.value;
      redactions += result.redactions;
    }

    return {
      value: sanitizedObject,
      redactions,
    };
  }

  return {
    value,
    redactions: 0,
  };
}

export default function SanitizedPayloadInspector() {
  const [copied, setCopied] = useState(false);

  const sanitized = useMemo(
    () => sanitizeValue(DEMO_PAYLOAD),
    [],
  );

  const formattedPayload = useMemo(
    () => JSON.stringify(sanitized.value, null, 2),
    [sanitized],
  );

  async function copySanitizedPayload() {
    try {
      await navigator.clipboard.writeText(formattedPayload);
      setCopied(true);

      window.setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 text-gray-900 shadow-sm sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-2">
            <FileJson size={22} className="text-blue-600" />
          </div>

          <div>
            <h2 className="text-lg font-bold">
              Sanitized Payload Inspector
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Synthetic JSON · Local demonstration
            </p>
          </div>
        </div>

        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
          <CheckCircle2 size={14} />
          Sanitized view
        </span>
      </header>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
        <div className="flex items-start gap-2">
          <ShieldAlert
            size={18}
            className="mt-0.5 shrink-0 text-amber-600"
          />

          <div>
            <p className="text-sm font-semibold text-amber-900">
              Demonstration only
            </p>

            <p className="mt-1 text-xs leading-5 text-amber-900/80">
              This example contains synthetic values. The sanitizer uses
              basic field-name and text-pattern rules. It cannot identify
              every form of sensitive information and is not a production
              security boundary.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs text-gray-500">
            Redactions applied
          </p>
          <p className="mt-1 text-2xl font-bold text-blue-600">
            {sanitized.redactions}
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs text-gray-500">
            Payload format
          </p>
          <p className="mt-1 flex items-center gap-2 text-sm font-semibold">
            <FileJson size={16} className="text-blue-600" />
            JSON
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 px-3 py-3">
          <div className="flex items-center gap-2">
            <Eye size={16} className="text-blue-600" />
            <h3 className="text-sm font-semibold">
              Sanitized JSON output
            </h3>
          </div>

          <button
            type="button"
            onClick={copySanitizedPayload}
            className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-medium hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {copied ? (
              <CheckCircle2 size={14} />
            ) : (
              <Copy size={14} />
            )}
            {copied ? "Copied" : "Copy sanitized JSON"}
          </button>
        </div>

        <pre className="max-h-[480px] overflow-auto rounded-b-lg bg-slate-50 p-4 text-xs leading-6 text-slate-800">
          <code>{formattedPayload}</code>
        </pre>
      </div>

      <p className="text-xs leading-5 text-gray-500">
        This panel renders the sanitized result only. In a production
        system, a trusted backend or processing layer should enforce
        data minimization before sensitive data reaches the browser.
      </p>
    </section>
  );
}
