const USER_KEY = "obliq_user_id";

export function getUserId() {
  return localStorage.getItem(USER_KEY);
}

export function setUserId(id) {
  if (id == null) localStorage.removeItem(USER_KEY);
  else localStorage.setItem(USER_KEY, String(id));
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const userId = getUserId();
  if (userId) headers["X-User-Id"] = userId;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  users: () => request("/api/users"),
  me: () => request("/api/me"),
  clients: () => request("/api/clients"),
  createClient: (name) => request("/api/clients", { method: "POST", body: JSON.stringify({ name }) }),
  client: (id) => request(`/api/clients/${id}`),
  documents: (clientId) =>
    request(clientId ? `/api/documents?client_id=${clientId}` : "/api/documents"),
  document: (id) => request(`/api/documents/${id}`),
  createDocument: (client_id, doc_type) =>
    request("/api/documents", { method: "POST", body: JSON.stringify({ client_id, doc_type }) }),
  createDocumentWithFile: (client_id, doc_type, file) => {
    const body = new FormData();
    body.append("client_id", String(client_id));
    body.append("doc_type", doc_type);
    body.append("file", file);
    return request("/api/documents/with-file", { method: "POST", body });
  },
  upload: (id, file) => {
    const body = new FormData();
    body.append("file", file);
    return request(`/api/documents/${id}/upload`, { method: "POST", body });
  },
  startReview: (id) => request(`/api/documents/${id}/start-review`, { method: "POST" }),
  approve: (id) => request(`/api/documents/${id}/approve`, { method: "POST" }),
  requestCorrection: (id, comment) =>
    request(`/api/documents/${id}/request-correction`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),
  documentAudit: (id) => request(`/api/documents/${id}/audit`),
  firmAudit: () => request("/api/audit"),
  download: async (id, versionId, filename) => {
    const userId = getUserId();
    const url = versionId
      ? `/api/documents/${id}/download?version_id=${versionId}`
      : `/api/documents/${id}/download`;
    const res = await fetch(url, { headers: userId ? { "X-User-Id": userId } : {} });
    if (!res.ok) {
      throw new Error(res.status === 404 ? "Document not found" : "Download failed");
    }
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename || "document";
    a.click();
    URL.revokeObjectURL(href);
  },
};
