const BASE = '/api';

let _getToken = null;

export function setTokenGetter(fn) {
  _getToken = fn;
}

async function authFetch(url, options = {}) {
  const headers = { ...options.headers };
  if (_getToken) {
    try {
      const token = await _getToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
    } catch (e) {
      console.error('[AUTH] Failed to get token:', e);
    }
  }
  const res = await fetch(url, { ...options, headers });
  // If 401 and we have a token getter, retry once (token may not have been ready)
  if (res.status === 401 && _getToken) {
    try {
      const token = await _getToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
      return fetch(url, { ...options, headers });
    } catch { /* give up */ }
  }
  return res;
}

export async function fetchProperties(filters = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const res = await authFetch(`${BASE}/properties?${params}`);
  return res.json();
}

export async function fetchStats() {
  const res = await authFetch(`${BASE}/stats`);
  return res.json();
}

export async function getEquity(propertyId) {
  const res = await authFetch(`${BASE}/properties/${propertyId}/equity`, {
    method: 'POST',
  });
  return res.json();
}

export async function fetchLeads(status = null) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  const res = await authFetch(`${BASE}/leads?${params}`);
  return res.json();
}

export async function createLead(propertyId) {
  const res = await authFetch(`${BASE}/properties/${propertyId}/create-lead`, {
    method: 'POST',
  });
  return res.json();
}

export async function bulkCreateLeads(propertyIds) {
  const res = await authFetch(`${BASE}/leads/bulk-create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ property_ids: propertyIds }),
  });
  return res.json();
}

export async function updateLead(leadId, updates) {
  const res = await authFetch(`${BASE}/leads/${leadId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function sendMessage(leadId, channel, to, body, subject = '') {
  const res = await authFetch(`${BASE}/messages/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_id: leadId, channel, to, body, subject }),
  });
  return res.json();
}

export async function getMessages(leadId) {
  const res = await authFetch(`${BASE}/messages/${leadId}`);
  return res.json();
}

export async function getShortCode(propertyId) {
  const res = await authFetch(`${BASE}/properties/${propertyId}/short-code`, {
    method: 'POST',
  });
  return res.json();
}

export async function getMessagingStatus() {
  const res = await authFetch(`${BASE}/messaging/status`);
  return res.json();
}

export async function fetchSmsTemplates() {
  const res = await authFetch(`${BASE}/sms-templates`);
  return res.json();
}

export async function createSmsTemplate(label, body) {
  const res = await authFetch(`${BASE}/sms-templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label, body }),
  });
  return res.json();
}

export async function updateSmsTemplate(id, updates) {
  const res = await authFetch(`${BASE}/sms-templates/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function deleteSmsTemplate(id) {
  const res = await authFetch(`${BASE}/sms-templates/${id}`, {
    method: 'DELETE',
  });
  return res.json();
}

export async function fetchQuoMessages(phone) {
  const res = await authFetch(`${BASE}/quo/messages?phone=${encodeURIComponent(phone)}`);
  return res.json();
}

export async function sendQuoMessage(leadId, to, content) {
  const res = await authFetch(`${BASE}/quo/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_id: leadId, to, content }),
  });
  return res.json();
}

export async function addLeadPhone(leadId, phone, type = '') {
  const res = await authFetch(`${BASE}/leads/${leadId}/phones`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, type }),
  });
  return res.json();
}

export async function updateLeadPhone(leadId, phoneId, updates) {
  const res = await authFetch(`${BASE}/leads/${leadId}/phones/${phoneId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function removeLeadPhone(leadId, phoneId) {
  const res = await authFetch(`${BASE}/leads/${leadId}/phones/${phoneId}`, {
    method: 'DELETE',
  });
  return res.json();
}

export async function refreshData() {
  const res = await authFetch(`${BASE}/refresh`, { method: 'POST' });
  return res.json();
}

export async function fetchNotifications(unreadOnly = false) {
  const params = new URLSearchParams();
  if (unreadOnly) params.set('unread_only', 'true');
  const res = await authFetch(`${BASE}/notifications?${params}`);
  return res.json();
}

export async function fetchUnreadCount() {
  const res = await authFetch(`${BASE}/notifications/unread-count`);
  return res.json();
}

export async function markNotificationRead(id) {
  const res = await authFetch(`${BASE}/notifications/${id}/read`, {
    method: 'PUT',
  });
  return res.json();
}
