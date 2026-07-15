/** Thin client for the Django /api backend (cookie session + CSRF). */

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function api(path, { method = 'GET', body, headers, signal } = {}) {
  const opts = {
    method,
    credentials: 'include',
    headers: { ...(headers || {}) },
    signal,
  };

  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }

  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCookie('csrftoken');
    if (csrf) opts.headers['X-CSRFToken'] = csrf;
  }

  const res = await fetch(`/api${path}`, opts);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }

  if (!res.ok) {
    const msg = data?.error || `${res.status} ${res.statusText}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

export function fetchMe() {
  return api('/auth/me');
}

export function loginUrl() {
  return '/api/auth/google/login';
}

export function logout() {
  return api('/auth/logout', { method: 'POST' });
}

export function getTransactionData({ page, source } = {}) {
  const params = new URLSearchParams();
  if (page != null) params.set('page', String(page));
  if (source) params.set('source', source);
  const qs = params.toString();
  return api(`/transactions${qs ? `?${qs}` : ''}`);
}

export function getMetadata() {
  return api('/metadata');
}

export function getIncomeExpenseByMonth() {
  return api('/income-expense');
}

export function getSpendingByCategory(month = 'all', { signal } = {}) {
  const params = new URLSearchParams({ month });
  return api(`/spending-by-category?${params}`, { signal });
}

export function addTransaction(payload) {
  return api('/transactions', { method: 'POST', body: payload });
}

export function addTransfer(payload) {
  return api('/transfers', { method: 'POST', body: payload });
}

export function addReceipt(payload) {
  return api('/receipts', { method: 'POST', body: payload });
}

export function getReceipt(id) {
  return api(`/receipts/${encodeURIComponent(id)}`);
}

export function parseFinanceMessage({ message, metadata }) {
  return api('/assistant/parse', { method: 'POST', body: { message, metadata } });
}

export function extractReceiptFromImage({ imageDataUrl, metadata }) {
  return api('/receipts/ocr', { method: 'POST', body: { imageDataUrl, metadata } });
}

export async function fetchHealth() {
  const opts = {
    method: 'GET',
    credentials: 'include',
    headers: {},
  };

  const res = await fetch('/api/health', opts);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }

  if (!res.ok && res.status !== 503) {
    const msg = data?.error || `${res.status} ${res.statusText}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

export function fetchManagementStatus() {
  return api('/management/status');
}

export function syncManagement() {
  return api('/management/sync', { method: 'POST' });
}
