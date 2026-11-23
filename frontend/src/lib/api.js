// Thin fetch wrapper for the backend's /api routes.
import { TOKEN_KEY, load } from "./storage.js";

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export function token() { return load(TOKEN_KEY) || ""; }

/**
 * api("/api/summary")
 * api("/api/config", { method: "PUT", json: {...} })
 * api("/api/documents/ITC", { method: "POST", body: formData })
 */
export async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {}, { Authorization: "Bearer " + token() });
  const init = Object.assign({}, opts, { headers });
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.json);
    delete init.json;
  }
  const res = await fetch(path, init);
  if (res.status === 401) { onUnauthorized(); throw new Error("Access token missing or wrong"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : d ? JSON.stringify(d) : res.statusText);
  }
  return data;
}
