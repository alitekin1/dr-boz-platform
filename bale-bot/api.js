/**
 * Tiny HTTP client for the Open WebUI backend.
 * Wraps the service-to-service calls the bot needs.
 */

const BACKEND = process.env.BACKEND_URL || 'http://open-webui:8080';
const SECRET = process.env.BOT_SHARED_SECRET || '';

const baseHeaders = (extra = {}) => ({
  'X-Bot-Secret': SECRET,
  'Content-Type': 'application/json',
  ...extra,
});

const adminHeaders = (adminId) => ({
  'X-Bot-Secret': SECRET,
  'X-Bot-Admin-Id': String(adminId),
  'Content-Type': 'application/json',
});

async function req(path, { method = 'GET', body, headers } = {}) {
  const res = await fetch(`${BACKEND}${path}`, {
    method,
    headers: headers || baseHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* not json */ }
  if (!res.ok) {
    const msg = json?.detail || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.body = json;
    throw err;
  }
  return json;
}

export const api = {
  // ─── Plans (no auth) ──────────────────────────────────────────
  listPlans: () => req('/api/v1/billing/public/plans'),

  // ─── Orders (bot auth) ────────────────────────────────────────
  createOrder: (data) => req('/api/v1/billing/orders', { method: 'POST', body: data }),
  getOrder:   (id)   => req(`/api/v1/billing/orders/${id}`),
  markPaid:   (id)   => req(`/api/v1/billing/orders/${id}/mark-paid`, { method: 'POST' }),
  cancelOrder:(id)   => req(`/api/v1/billing/orders/${id}/cancel`,   { method: 'POST' }),

  // ─── Admin (admin auth) ───────────────────────────────────────
  adminCreateOrder: (adminId, data) =>
    req('/api/v1/billing/admin/orders', { method: 'POST', body: data, headers: adminHeaders(adminId) }),
  adminListPending: (adminId) =>
    req('/api/v1/billing/admin/orders/pending-card', { headers: adminHeaders(adminId) }),
  adminApprove: (adminId, orderId) =>
    req(`/api/v1/billing/admin/orders/${orderId}/approve`, { method: 'POST', headers: adminHeaders(adminId) }),
  adminReject:  (adminId, orderId) =>
    req(`/api/v1/billing/admin/orders/${orderId}/reject`,  { method: 'POST', headers: adminHeaders(adminId) }),
};

export { BACKEND };
