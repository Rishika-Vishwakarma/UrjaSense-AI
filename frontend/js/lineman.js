/* Lineman dashboard */
const me = Auth.guard("lineman");
setupShell();
document.getElementById("userchip").textContent = me ? me.full_name : "";
let selected = null;           // incident id chosen in "Assigned Incidents"
let CATS = [];

const NEXT = { ASSIGNED: "REPAIR_IN_PROGRESS", REPAIR_IN_PROGRESS: "RESOLVED" };

function incidentOptions(list) {
  return list.filter(i => i.status !== "RESOLVED").map(i => `<option value="${i.id}" ${i.id === selected ? "selected" : ""}>${esc(i.incident_code)} — ${esc(i.area_name)}</option>`).join("");
}
function incidentCard(i) {
  return `<div class="incident-card"><header><div><b>${esc(i.incident_code)}</b> · ${esc(i.area_name)}${sampleBadge(i.is_sample)}</div>
    <div>${priorityBadge(i.priority)} ${statusBadge(i.status)}</div></header>${stepper(i.status)}
    <div class="kv"><div><b>${esc(t("location", "Location"))}</b>${esc(i.location_text || "—")}</div>
    <div><b>${esc(t("residents", "Residents affected"))}</b>${esc(i.affected_count)}</div>
    <div><b>Started</b>${fmt(i.outage_start_time)}</div>${estimateHtml(i)}</div>
    <button class="btn btn-primary btn-sm" data-open="${i.id}">${esc(t("nav_details", "Details"))}</button></div>`;
}
function bindOpen(el) { el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { selected = +b.dataset.open; router.go("details"); }); }

const views = {
  async overview(el) {
    const [o, { incidents }] = await Promise.all([api("/lineman/overview"), api("/lineman/incidents")]);
    el.innerHTML = `<div class="cards">${statCard(t("assigned_to_me", "Assigned to me (open)"), o.active, "", true)}
      ${statCard(t("urgent", "High / critical priority"), o.urgent)}${statCard(t("residents_affected", "Residents affected"), o.residents_affected)}
      ${statCard(t("resolved", "Resolved"), o.resolved)}</div>
      <div class="panel"><h2>Next up</h2>${incidents.filter(i => i.status !== "RESOLVED").slice(0, 3).map(incidentCard).join("") || `<div class="empty">No open incidents assigned to you.</div>`}</div>`;
    bindOpen(el);
  },
  async assigned(el) {
    const { incidents } = await api("/lineman/incidents");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_assigned">Assigned Incidents</h2>
      ${incidents.length ? incidents.map(incidentCard).join("") : `<div class="empty">No incidents assigned yet. An administrator assigns incidents to you.</div>`}</div>`;
    bindOpen(el);
  },
  async details(el) {
    const { incidents } = await api("/lineman/incidents");
    if (!selected || !incidents.some(i => i.id === selected)) selected = incidents.find(i => i.status !== "RESOLVED")?.id || incidents[0]?.id;
    if (!selected) { el.innerHTML = `<div class="panel empty">No incident selected.</div>`; return; }
    const r = await api("/lineman/incidents/" + selected);
    CATS = r.categories; const i = r.incident;
    el.innerHTML = `<div class="toolbar"><div class="field"><label for="pick">Incident</label><select id="pick">${incidents.map(x => `<option value="${x.id}" ${x.id === selected ? "selected" : ""}>${esc(x.incident_code)} — ${esc(x.area_name)}</option>`).join("")}</select></div></div>
      <div class="two"><div class="panel"><h2>${esc(i.incident_code)} · ${esc(i.area_name)}</h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap">${priorityBadge(i.priority)} ${statusBadge(i.status)}${sampleBadge(i.is_sample)}</div>${stepper(i.status)}
        <div class="kv"><div><b>${esc(t("residents", "Residents affected"))}</b>${esc(i.affected_count)}</div><div><b>Location</b>${esc(i.location_text || "—")}</div>
        <div><b>GPS</b>${i.latitude != null ? esc(i.latitude + ", " + i.longitude) : "Not shared"}</div><div><b>Started</b>${fmt(i.outage_start_time)}</div>
        <div><b>${esc(t("suggested_cat", "Suggested category (automatic, not verified)"))}</b>${esc(catText(i.suggested_category))} <span class="badge est">Unverified</span></div>
        <div><b>Verified category</b>${i.verified_category ? esc(catText(i.verified_category)) : "—"}</div>
        <div><b>${esc(t("official_cause", "Verified cause"))}</b>${esc(i.official_cause || "—")}</div><div><b>Repair progress</b>${esc(i.repair_progress_pct)}%</div>${estimateHtml(i)}</div>
        ${i.status !== "RESOLVED" ? `<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-primary btn-sm" id="to-status">${esc(t("nav_status", "Update status"))}</button>
          <button class="btn btn-outline btn-sm" id="to-eta">${esc(t("nav_eta", "Update restoration time"))}</button></div>` : ""}</div>
      <div class="panel"><h2>Timeline</h2>${timeline(r.updates)}</div></div>
      <div class="panel"><h2>Resident reports (${r.reports.length})</h2>${table([{ h: "Report", f: x => esc(x.report_code) }, { h: "Location", f: x => esc(x.location_text) },
        { h: "Details", f: x => esc(x.issue_details || "—") }, { h: "Started", f: x => fmt(x.outage_start_time) }], r.reports)}</div>`;
    el.querySelector("#pick").onchange = e => { selected = +e.target.value; router.go("details"); };
    el.querySelector("#to-status")?.addEventListener("click", () => router.go("status"));
    el.querySelector("#to-eta")?.addEventListener("click", () => router.go("eta"));
  },
  async status(el) {
    const { incidents } = await api("/lineman/incidents");
    const open = incidents.filter(i => i.status !== "RESOLVED");
    if (!open.length) { el.innerHTML = `<div class="panel empty">No open incidents to update.</div>`; return; }
    if (!open.some(i => i.id === selected)) selected = open[0].id;
    const cur = open.find(i => i.id === selected), next = NEXT[cur.status];
    el.innerHTML = `<div class="panel" style="max-width:640px"><h2 data-i18n="update_status">Update incident status</h2>
      <form id="f"><div class="field"><label for="inc">Incident</label><select id="inc">${incidentOptions(incidents)}</select></div>
      <p>Current status: ${statusBadge(cur.status)}</p>
      ${next ? `<div class="field"><label for="st" data-i18n="new_status">New status</label><select id="st"><option value="${next}">${esc(statusText(next))}</option></select>
        <span class="hint">Workflow: Reported → Verified → Assigned → Repair in progress → Resolved. Only the next step is allowed.</span></div>
        <div class="field"><label for="rm" data-i18n="remarks">Remarks</label><textarea id="rm" maxlength="1000" placeholder="What was done / found?"></textarea></div>
        <p class="error-text" id="err"></p><button class="btn btn-primary" data-i18n="update">Update</button>`
        : `<p>No further status step available for you.</p>`}</form></div>`;
    el.querySelector("#inc").onchange = e => { selected = +e.target.value; router.go("status"); };
    el.querySelector("#f").onsubmit = async e => { e.preventDefault();
      if (!confirm(`Change status to "${statusText(next)}"? Residents of this incident will be notified.`)) return;
      try { await api(`/lineman/incidents/${selected}/status`, { method: "POST", body: { status: next, remarks: el.querySelector("#rm").value } });
        toast("Status updated and residents notified", "success"); router.go("status"); } catch (x) { el.querySelector("#err").textContent = x.message; } };
  },
  async eta(el) {
    const { incidents } = await api("/lineman/incidents");
    const open = incidents.filter(i => i.status !== "RESOLVED");
    if (!open.length) { el.innerHTML = `<div class="panel empty">No open incidents to update.</div>`; return; }
    if (!open.some(i => i.id === selected)) selected = open[0].id;
    const cur = open.find(i => i.id === selected);
    if (!CATS.length) CATS = (await api("/lineman/incidents/" + selected)).categories;
    const d = new Date(Date.now() + 90 * 60000); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    el.innerHTML = `<div class="panel" style="max-width:700px"><h2 data-i18n="nav_eta">Update restoration time</h2>
      <form id="f"><div class="field"><label for="inc">Incident</label><select id="inc">${incidentOptions(incidents)}</select></div>
      <div class="field"><label for="eta" data-i18n="set_eta">Restoration time (your confirmed ETA)</label><input id="eta" type="datetime-local" value="${d.toISOString().slice(0, 16)}"></div>
      <div class="field"><label for="pct" data-i18n="progress">Repair progress (%)</label><input id="pct" type="number" min="0" max="100" value="${cur.repair_progress_pct}"></div>
      <div class="field"><label for="vc">Verified category</label><select id="vc"><option value="">— not changed —</option>${CATS.map(c => `<option value="${c}" ${cur.verified_category === c ? "selected" : ""}>${esc(catText(c))}</option>`).join("")}</select></div>
      <div class="field"><label for="oc" data-i18n="verified_cause">Verified outage reason (authorised employees only)</label><input id="oc" maxlength="255" value="${esc(cur.official_cause || "")}" placeholder="e.g. Transformer fuse blown, replaced"></div>
      <div class="field"><label for="rm" data-i18n="remarks">Repair progress note</label><textarea id="rm" maxlength="1000"></textarea></div>
      <p class="error-text" id="err"></p><button class="btn btn-primary" data-i18n="save">Save</button></form></div>`;
    el.querySelector("#inc").onchange = e => { selected = +e.target.value; router.go("eta"); };
    el.querySelector("#f").onsubmit = async e => { e.preventDefault();
      const body = { repair_progress_pct: +el.querySelector("#pct").value, remarks: el.querySelector("#rm").value };
      if (el.querySelector("#eta").value) body.lineman_eta_at = el.querySelector("#eta").value;
      if (el.querySelector("#oc").value.trim()) body.official_cause = el.querySelector("#oc").value;
      if (el.querySelector("#vc").value) body.verified_category = el.querySelector("#vc").value;
      try { await api(`/lineman/incidents/${selected}/progress`, { method: "POST", body }); toast("Update saved and residents notified", "success"); router.go("eta"); }
      catch (x) { el.querySelector("#err").textContent = x.message; } };
  },
  async repairs(el) {
    const { history } = await api("/lineman/history");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_repairs">Repair History</h2>${table([
      { h: "When", f: r => fmt(r.update_at) }, { h: "Incident", f: r => esc(r.incident_code) }, { h: t("area", "Area"), f: r => esc(r.area_name) },
      { h: t("status", "Status"), f: r => statusBadge(r.new_status) }, { h: "Remarks", f: r => esc(r.remarks || "—") }], history, "No repair updates yet")}</div>`;
  },
  async profile(el) {
    const { profile: p } = await api("/lineman/profile");
    el.innerHTML = `<div class="panel" style="max-width:640px"><h2 data-i18n="nav_profile">Profile</h2><div class="kv">
      <div><b>Name</b>${esc(p.full_name)}</div><div><b>Employee code</b>${esc(p.employee_code)}</div><div><b>Designation</b>${esc(p.designation)}</div>
      <div><b>Email</b>${esc(p.email)}</div><div><b>Phone</b>${esc(p.phone || "—")}</div><div><b>Home area</b>${esc(p.area_name || "—")}</div>
      <div><b>Approval</b><span class="badge ok">${esc(p.approval_status)}</span></div></div>
      <p class="hint" style="color:var(--muted)">Employee accounts are created and approved by administrators.</p></div>`;
  },
};
const router = makeRouter(views, "overview");
langSelect(() => router.go(router.current()));
applyI18n();
router.go(location.hash.slice(1) || "overview");
