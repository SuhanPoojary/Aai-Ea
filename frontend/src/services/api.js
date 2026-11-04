
const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8001/api")
  .replace(/\/$/, "");

let token = localStorage.getItem("aegis_access_token") || "";

export function setAccessToken(value) {
  token = value || "";
  if (token) localStorage.setItem("aegis_access_token", token);
  else localStorage.removeItem("aegis_access_token");
}

export function getAccessToken() {
  return token;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new Error("Cannot reach AegisSupport API. Check that FastAPI is running on port 8001.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch {
      // Use fallback message for non-JSON errors.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

const json = (method, body) => ({
  method,
  body: JSON.stringify(body),
});

export const api = {
  // Existing supervisor APIs
  health: () => request("/health"),
  customers: () => request("/customers"),
  orders: id => request(`/orders/${encodeURIComponent(id)}`),
  chat: body => request("/chat", json("POST", body)),
  tickets: () => request("/tickets"),
  updateTicket: (id, status) =>
    request(`/tickets/${encodeURIComponent(id)}`, json("PATCH", { status })),
  analytics: () => request("/analytics"),
  events: () => request("/events"),
  knowledge: () => request("/knowledge"),

  // Customer authentication
  login: credentials => request("/auth/login", json("POST", credentials)),
  supervisorLogin: credentials => request("/auth/supervisor/login", json("POST", credentials)),
  register: details => request("/auth/register", json("POST", details)),
  me: () => request("/auth/me"),

  // Customer-specific endpoints
  myOrders: () => request("/my/orders"),
  myChat: body => request("/my/chat", json("POST", body)),
};
