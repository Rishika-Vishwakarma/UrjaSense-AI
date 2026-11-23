/* Shared helpers: API client, auth session, i18n, toasts, modal, formatting. */
const API = (window.URJA_API_BASE || "") + "/api";

/* ---------- i18n ---------- */
const Lang = {
  get() { try { return localStorage.getItem("urja_lang") || "en"; } catch { return "en"; } },
  set(l) { try { localStorage.setItem("urja_lang", l); } catch {} document.documentElement.lang = l; },
};
function t(key, fallback) {
  const l = Lang.get();
  return (window.I18N[l] && window.I18N[l][key]) || fallback || key;
}
function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach(el => {
    if (!el.dataset.en) el.dataset.en = el.innerHTML;
    const v = window.I18N[Lang.get()][el.dataset.i18n];
    el.innerHTML = v || el.dataset.en;
  });
  root.querySelectorAll("[data-i18n-ph]").forEach(el => {
    if (!el.dataset.enPh) el.dataset.enPh = el.placeholder;
    el.placeholder = window.I18N[Lang.get()][el.dataset.i18nPh] || el.dataset.enPh;
  });
}
function langSelect(onChange) {
  const sel = document.querySelector(".lang-select");
  if (!sel) return;
  sel.innerHTML = Object.entries(window.LANGS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  sel.value = Lang.get();
  sel.setAttribute("aria-label", "Language");
  sel.addEventListener("change", async () => {
    Lang.set(sel.value); applyI18n();
    if (Auth.token()) { try { await api("/auth/me", { method: "PUT", body: { preferred_language: sel.value } }); } catch {} }
    onChange && onChange(sel.value);
  });
}

/* ---------- safety: escape everything that came from the server ---------- */
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- auth session ---------- */
const Auth = {
  token() { try { return localStorage.getItem("urja_token"); } catch { return null; } },
  user() { try { return JSON.parse(localStorage.getItem("urja_user") || "null"); } catch { return null; } },
  save(token, user) { try { localStorage.setItem("urja_token", token); localStorage.setItem("urja_user", JSON.stringify(user)); } catch {} },
  clear() { try { localStorage.removeItem("urja_token"); localStorage.removeItem("urja_user"); } catch {} },
  home(role) { return { public: "user-dashboard.html", lineman: "lineman-dashboard.html", admin: "admin-dashboard.html" }[role]; },
  /* Redirects away unless the logged-in user has the right role. (Real enforcement is on the server.) */
  guard(role) {
    const u = this.user();
    if (!this.token() || !u) { location.href = "../login.html"; return null; }
    if (u.role !== role) { location.href = this.home(u.role); return null; }
    if (u.preferred_language && !localStorage.getItem("urja_lang")) Lang.set(u.preferred_language);
    return u;
  },
  logout() { this.clear(); location.href = location.pathname.includes("/dashboards/") ? "../login.html" : "login.html"; },
};

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && Auth.token()) headers.Authorization = "Bearer " + Auth.token();
  let res;
  try { res = await fetch(API + path, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
  catch { throw new Error("Cannot reach the server. Is the backend running?"); }
  let data = {};
  try { data = await res.json(); } catch {}
  if (res.status === 401 && auth && Auth.token()) { Auth.clear(); location.href = (location.pathname.includes("/dashboards/") ? "../" : "") + "login.html"; }
  if (!res.ok) { const e = new Error(data.error || `Request failed (${res.status})`); e.status = res.status; e.data = data; throw e; }
  return data;
}

/* ---------- UI helpers ---------- */
function toast(msg, type = "info") {
  let box = document.getElementById("toasts");
  if (!box) { box = document.createElement("div"); box.id = "toasts"; box.setAttribute("aria-live", "polite"); document.body.appendChild(box); }
  const el = document.createElement("div");
  el.className = "toast " + type; el.textContent = msg; box.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}
function openModal(title, html) {
  closeModal();
  const bg = document.createElement("div");
  bg.className = "modal-bg"; bg.id = "modal-bg";
  bg.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><header><h2>${esc(title)}</h2>
    <button class="btn btn-outline btn-sm" id="modal-x" aria-label="Close">✕</button></header><div id="modal-body">${html}</div></div>`;
  bg.addEventListener("click", e => { if (e.target === bg) closeModal(); });
  document.body.appendChild(bg);
  document.getElementById("modal-x").onclick = closeModal;
  document.addEventListener("keydown", escClose);
  return document.getElementById("modal-body");
}
function escClose(e) { if (e.key === "Escape") closeModal(); }
function closeModal() { document.getElementById("modal-bg")?.remove(); document.removeEventListener("keydown", escClose); }

const STATUS_FLOW = ["REPORTED", "VERIFIED", "ASSIGNED", "REPAIR_IN_PROGRESS", "RESOLVED"];
const STATUS_EN = { REPORTED: "Reported", VERIFIED: "Verified", ASSIGNED: "Assigned", REPAIR_IN_PROGRESS: "Repair in progress", RESOLVED: "Resolved" };
const PRIORITY_EN = { LOW: "Low", MEDIUM: "Medium", HIGH: "High", CRITICAL: "Critical" };
const CAT_EN = { transformer_fault: "Transformer issue", line_fault: "Line / wire fault", weather_related: "Weather related",
  planned_maintenance: "Planned maintenance", local_fault: "Local / household fault", other: "Other", unknown: "Unknown" };

const statusText = s => t(s, STATUS_EN[s] || s);
const priorityText = p => t(p, PRIORITY_EN[p] || p);
const catText = c => t(c, CAT_EN[c] || c);

function statusBadge(s) {
  const cls = s === "RESOLVED" ? "ok" : s === "REPORTED" ? "warn" : "";
  return `<span class="badge ${cls}">${esc(statusText(s))}</span>`;
}
function priorityBadge(p) {
  const cls = p === "CRITICAL" || p === "HIGH" ? "bad" : p === "MEDIUM" ? "warn" : "";
  return `<span class="badge ${cls}">${esc(priorityText(p))}</span>`;
}
function stepper(status) {
  const idx = STATUS_FLOW.indexOf(status);
  return `<div class="steps" role="img" aria-label="${esc(statusText(status))}">${STATUS_FLOW.map((_, i) => `<span class="${i <= idx ? "done" : ""}"></span>`).join("")}</div>`;
}
function fmt(dt) {
  if (!dt) return "—";
  const d = new Date(String(dt).replace(" ", "T"));
  if (isNaN(d)) return esc(dt);
  return d.toLocaleString(Lang.get() === "hi" ? "hi-IN" : "en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function mins(m) {
  if (m == null) return "—";
  m = Math.round(m);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
}
function sampleBadge(x) { return x ? ` <span class="badge sample" title="Simulated demo record">${esc(t("sample_badge", "Sample data"))}</span>` : ""; }
function table(cols, rows, empty = "No data") {
  if (!rows.length) return `<div class="empty">${esc(t("no_data", empty))}</div>`;
  return `<div class="table-wrap"><table><thead><tr>${cols.map(c => `<th>${c.h}</th>`).join("")}</tr></thead><tbody>${
    rows.map(r => `<tr>${cols.map(c => `<td>${c.f(r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function statCard(label, value, sub = "", accent = false) {
  return `<div class="stat ${accent ? "accent" : ""}"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>`;
}
function timeline(updates) {
  if (!updates.length) return `<div class="empty">No updates yet</div>`;
  return `<ul class="timeline">${updates.map(u => `<li><b>${esc(statusText(u.new_status))}</b>
    <small>${fmt(u.created_at)}${u.updated_by_name ? " · " + esc(u.updated_by_name) : ""}</small>${u.remarks ? `<div>${esc(u.remarks)}</div>` : ""}</li>`).join("")}</ul>`;
}
function estimateHtml(inc) {
  if (inc.status === "RESOLVED") return "";
  const lm = inc.lineman_eta_at
    ? `<div><b>${esc(t("est_restore", "Restoration time"))} (lineman)</b>${fmt(inc.lineman_eta_at)} <span class="badge ok">Confirmed</span></div>` : "";
  const ai = inc.predicted_restoration_at
    ? `<div><b>${esc(t("est_restore", "Estimated restoration"))}</b>${fmt(inc.predicted_restoration_at)} <span class="badge est">${esc(t("estimate", "Estimate"))}</span>
       <div class="hint" style="font-size:.8rem;color:var(--muted)">${esc(t("est_note", "Model estimate, not an official commitment."))}</div></div>` : "";
  return lm + ai;
}
function setupShell(titleKey) {
  const menu = document.getElementById("menu-btn"), sb = document.querySelector(".sidebar");
  menu?.addEventListener("click", () => sb.classList.toggle("open"));
  document.getElementById("logout-btn")?.addEventListener("click", () => Auth.logout());
}
function makeRouter(views, defaultView) {
  const nav = document.querySelectorAll(".nav-item[data-view]");
  async function go(view, arg) {
    if (!views[view]) view = defaultView;
    nav.forEach(n => n.classList.toggle("active", n.dataset.view === view));
    const title = document.querySelector(`.nav-item[data-view="${view}"] span[data-i18n]`);
    document.getElementById("page-title").textContent = title ? title.textContent : view;
    document.querySelector(".sidebar")?.classList.remove("open");
    const el = document.getElementById("view");
    el.innerHTML = `<div class="loading">Loading…</div>`;
    try { await views[view](el, arg); applyI18n(el); }
    catch (e) { el.innerHTML = `<div class="panel"><b>Something went wrong.</b><p class="error-text">${esc(e.message)}</p></div>`; }
    history.replaceState(null, "", "#" + view);
    window.__view = view; window.__viewArg = arg;
  }
  nav.forEach(n => n.addEventListener("click", () => go(n.dataset.view)));
  window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (v && v !== window.__view) go(v); });
  return { go, current: () => window.__view };
}
const charts = {};
function drawChart(id, cfg) {
  if (typeof Chart === "undefined") { document.getElementById(id)?.replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: "Chart library failed to load" })); return; }
  charts[id]?.destroy();
  const el = document.getElementById(id); if (!el) return;
  cfg.options = Object.assign({ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: cfg.type === "doughnut" } } }, cfg.options || {});
  charts[id] = new Chart(el, cfg);
}
const PALETTE = ["#1565D8", "#64B5F6", "#0B1F3A", "#8CC4F8", "#3B83E0", "#2A4A7C"];
