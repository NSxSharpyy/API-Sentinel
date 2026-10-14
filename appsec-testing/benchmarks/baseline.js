import http from 'k6/http';
import { check, fail, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const AUTH_URL = __ENV.AUTH_URL || 'http://127.0.0.1:5001';
const USER_URL = __ENV.USER_URL || 'http://127.0.0.1:5002';
const ORDER_URL = __ENV.ORDER_URL || 'http://127.0.0.1:5003';
const BILLING_URL = __ENV.BILLING_URL || 'http://127.0.0.1:5004';

const PASSWORD = __ENV.DEMO_PASSWORD || 'Password123!';
const USERNAMES = (__ENV.USERNAMES || 'alice.anderson1').split(',')
  .map((name) => name.trim())
  .filter(Boolean);

const errors = new Rate('benchmark_errors');

const loginDuration = new Trend('login_duration_ms');
const verifyDuration = new Trend('verify_duration_ms');
const profileDuration = new Trend('profile_duration_ms');
const ordersDuration = new Trend('orders_duration_ms');
const invoiceDuration = new Trend('invoice_duration_ms');

const loginSamples = new Counter('login_samples');
const verifySamples = new Counter('verify_samples');
const profileSamples = new Counter('profile_samples');
const ordersSamples = new Counter('orders_samples');
const invoiceSamples = new Counter('invoice_samples');


export const options = {
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    api_baseline: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    benchmark_errors: ['rate<0.01'],
    checks: ['rate>0.99'],
    // This is a target to validate against the observed baseline.
    http_req_duration: ['p(95)<50'],
  },
};

function params(endpoint, token) {
  const headers = { Accept: 'application/json' };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return {
    headers,
    timeout: '10s',
    tags: { endpoint },
  };
}

function recordCheck(response, name, expectedStatus = 200) {
  const passed = check(response, {
    [`${name}: HTTP ${expectedStatus}`]: (r) =>
      r.status === expectedStatus,
  });

  errors.add(!passed);
  return passed;
}

export default function () {
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
      tags: { endpoint: 'login' },
    },
  );

  loginDuration.add(login.timings.duration);
  loginSamples.add(1);

  if (!recordCheck(login, 'login')) {
    fail(`Login failed with HTTP ${login.status}`);
  }

  let loginData;

  try {
    loginData = login.json();
  } catch (_) {
    fail('Login response was not valid JSON');
  }

  const token = loginData.token;
  const userId = loginData.user_id;

  if (!token || userId === undefined || userId === null) {
    fail('Login response did not contain token and user_id');
  }

  const verify = http.get(
    `${AUTH_URL}/api/v2/auth/verify`,
    params('verify', token),
  );

  verifyDuration.add(verify.timings.duration);
  verifySamples.add(1);

  if (!recordCheck(verify, 'verify')) {
    fail(`Token verification failed with HTTP ${verify.status}`);
  }

  let verifyData;

  try {
    verifyData = verify.json();
  } catch (_) {
    fail('Verify response was not valid JSON');
  }

  const valid = check(verifyData, {
    'verify: token is valid': (data) => data.valid === true,
  });

  errors.add(!valid);

  if (!valid) {
    fail('Token verification returned valid=false');
  }

  const profile = http.get(
    `${USER_URL}/api/v2/users/me`,
    params('get_profile', token),
  );

  profileDuration.add(profile.timings.duration);
  profileSamples.add(1);

  if (!recordCheck(profile, 'get_profile')) {
    fail(`Profile request failed with HTTP ${profile.status}`);
  }

  const orders = http.get(
    `${ORDER_URL}/api/v2/orders`,
    params('list_orders', token),
  );

  ordersDuration.add(orders.timings.duration);
  ordersSamples.add(1);

  if (!recordCheck(orders, 'list_orders')) {
    fail(`Orders request failed with HTTP ${orders.status}`);
  }

  const invoiceList = http.get(
    `${BILLING_URL}/api/v2/billing/invoices`,
    params('list_invoices', token),
  );

  if (!recordCheck(invoiceList, 'list_invoices')) {
    fail(`Invoice list failed with HTTP ${invoiceList.status}`);
  }

  let invoiceData;

  try {
    invoiceData = invoiceList.json();
  } catch (_) {
    fail('Invoice list response was not valid JSON');
  }

  const invoices = invoiceData.invoices;

  if (!Array.isArray(invoices)) {
    fail('Invoice list response did not contain an invoices array');
  }

  const ownedInvoices = invoices.filter(
    (invoice) => String(invoice.owner_id) === String(userId),
  );

  if (ownedInvoices.length === 0) {
    fail('No invoice owned by the authenticated customer was found');
  }

  const invoice = ownedInvoices[0];

  const invoiceResponse = http.get(
    `${BILLING_URL}/api/v2/billing/invoices/${encodeURIComponent(invoice.id)}`,
    params('get_invoice', token),
  );

  invoiceDuration.add(invoiceResponse.timings.duration);
  invoiceSamples.add(1);

  if (!recordCheck(invoiceResponse, 'get_invoice')) {
    fail(`Invoice request failed with HTTP ${invoiceResponse.status}`);
  }

  sleep(0.5);
}
