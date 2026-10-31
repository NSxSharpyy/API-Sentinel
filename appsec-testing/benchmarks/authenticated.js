import http from 'k6/http';
import { check, fail, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const AUTH_URL = __ENV.AUTH_URL || 'http://127.0.0.1:5001';
const USER_URL = __ENV.USER_URL || 'http://127.0.0.1:5002';
const ORDER_URL = __ENV.ORDER_URL || 'http://127.0.0.1:5003';
const BILLING_URL = __ENV.BILLING_URL || 'http://127.0.0.1:5004';

const PASSWORD = __ENV.DEMO_PASSWORD || 'Password123!';
const USERNAMES = (__ENV.USERNAMES || 'alice.anderson1')
  .split(',')
  .map((name) => name.trim())
  .filter(Boolean);

const errors = new Rate('benchmark_errors');
const loginDuration = new Trend('login_duration_ms');

let token;
let userId;

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    authenticated_api: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || '15s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    benchmark_errors: ['rate<0.01'],
    checks: ['rate>0.99'],
    'http_req_duration{workload:authenticated}': ['p(95)<50'],
  },
};

function params(endpoint) {
  return {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    timeout: '10s',
    tags: {
      endpoint,
      workload: 'authenticated',
    },
  };
}

function verifyStatus(response, label) {
  const passed = check(response, {
    [`${label}: HTTP 200`]: (r) => r.status === 200,
  });
  errors.add(!passed);

  if (!passed) {
    fail(`${label} failed with HTTP ${response.status}`);
  }
}

export default function () {
  // Each VU logs in once and reuses its own token for this short benchmark.
  // The login request is tagged separately from authenticated API latency.
  if (!token) {
    const username = USERNAMES[(__VU - 1) % USERNAMES.length];

    const login = http.post(
      `${AUTH_URL}/api/v2/auth/login`,
      JSON.stringify({ username, password: PASSWORD }),
      {
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        timeout: '10s',
        tags: {
          endpoint: 'login',
          workload: 'bootstrap',
        },
      },
    );

    loginDuration.add(login.timings.duration);

    const loginPassed = check(login, {
      'bootstrap login: HTTP 200': (r) => r.status === 200,
    });
    errors.add(!loginPassed);

    if (!loginPassed) {
      fail(`Bootstrap login failed with HTTP ${login.status}`);
    }

    let body;
    try {
      body = login.json();
    } catch (_) {
      fail('Bootstrap login response was not valid JSON');
    }

    if (!body.token || body.user_id === undefined || body.user_id === null) {
      fail('Bootstrap login response is missing token or user_id');
    }

    token = body.token;
    userId = body.user_id;
  }

  const verify = http.get(
    `${AUTH_URL}/api/v2/auth/verify`,
    params('verify'),
  );
  verifyStatus(verify, 'verify');

  const verifyBody = verify.json();
  const valid = check(verifyBody, {
    'verify: token is valid': (body) => body.valid === true,
  });
  errors.add(!valid);
  if (!valid) fail('Token verification returned valid=false');

  const profile = http.get(
    `${USER_URL}/api/v2/users/me`,
    params('get_profile'),
  );
  verifyStatus(profile, 'get_profile');

  const orders = http.get(
    `${ORDER_URL}/api/v2/orders`,
    params('list_orders'),
  );
  verifyStatus(orders, 'list_orders');

  const invoiceList = http.get(
    `${BILLING_URL}/api/v2/billing/invoices`,
    params('list_invoices'),
  );
  verifyStatus(invoiceList, 'list_invoices');

  let invoiceBody;
  try {
    invoiceBody = invoiceList.json();
  } catch (_) {
    fail('Invoice list response was not valid JSON');
  }

  if (!Array.isArray(invoiceBody.invoices)) {
    fail('Invoice list response did not contain an invoices array');
  }

  const ownedInvoice = invoiceBody.invoices.find(
    (invoice) => String(invoice.owner_id) === String(userId),
  );

  if (!ownedInvoice) {
    fail('No invoice owned by the authenticated customer was found');
  }

  const invoice = http.get(
    `${BILLING_URL}/api/v2/billing/invoices/${encodeURIComponent(ownedInvoice.id)}`,
    params('get_invoice'),
  );
  verifyStatus(invoice, 'get_invoice');

  sleep(0.5);
}
