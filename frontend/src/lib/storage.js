// localStorage wrappers that never throw (private mode, blocked storage, ...).
export const TOKEN_KEY = "sa_token";
export const TAB_KEY = "sa_tab";

export function store(key, value) {
  try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* ignore */ }
}

export function load(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}

/** If the page was opened with ?token=..., remember it and strip it from the address bar. */
export function captureTokenFromUrl() {
  const u = new URL(location.href);
  const t = u.searchParams.get("token");
  if (t) {
    store(TOKEN_KEY, t);
    u.searchParams.delete("token");
    history.replaceState(null, "", u.pathname + u.search + u.hash);
  }
}
