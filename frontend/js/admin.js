/* Administrator dashboard */
const me = Auth.guard("admin");
setupShell();
document.getElementById("userchip").textContent = me ? me.full_name : "";
let AREAS = [], LINEMEN = [];

async function loadRefs() {
  AREAS = (await api("/admin/areas")).areas;
  LINEMEN = (await api("/admin/linemen")).linemen;
}
const areaOpts = (sel) => AREAS.filter(a => a.is_active).map(a => `<option value="${a.id}" ${a.id === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
const lmOpts = () => LINEMEN.filter(l => l.approval_status === "APPROVED" && l.is_active)
  .map(l => `<option value="${l.id}">${esc(l.full_name)} (${esc(l.employee_code)}) · ${l.open_incidents} open</option>`).join("");

async function incidentModal(id) {
  const r = await api("/admin/incidents/" + id), i = r.incident;
  openModal(i.incident_code, `<div style="display:flex;gap:8px;flex-wrap:wrap">${statusBadge(i.status)} ${priorityBadge(i.priority)}${sampleBadge(i.is_sample)}</div>${stepper(i.status)}
    <div class="kv"><div><b>Area</b>${esc(i.area_name)}</div><div><b>Affected residents</b>${esc(i.affected_count)}</div><div><b>Assigned to</b>${esc(i.assigned_to || "—")}</div>
    <div><b>Suggested category (unverified)</b>${esc(catText(i.suggested_category))}</div><div><b>Verified cause</b>${esc(i.official_cause || "—")}</div>
    <div><b>Progress</b>${esc(i.repair_progress_pct)}%</div>${estimateHtml(i)}</div>
    <h3>Timeline</h3>${timeline(r.updates)}<h3>Resident reports (${r.reports.length})</h3>
    ${table([{ h: "Report", f: x => esc(x.report_code) }, { h: "Resident", f: x => esc(x.full_name) }, { h: "Details", f: x => esc(x.issue_details || "—") },
      { h: "Linked", f: x => x.matched_existing ? `Yes (score ${esc(x.match_score)})` : "First report" }], r.reports)}`);
}
function incidentRows(list, actions) {
  return table([
    { h: "Incident", f: i => `<a href="#" data-view-inc="${i.id}">${esc(i.incident_code)}</a>${sampleBadge(i.is_sample)}` },
    { h: "Area", f: i => esc(i.area_name) }, { h: "Status", f: i => statusBadge(i.status) }, { h: "Priority", f: i => priorityBadge(i.priority) },
    { h: "Affected", f: i => esc(i.affected_count) }, { h: "Assigned", f: i => esc(i.assigned_to || "—") },
    { h: "Started", f: i => fmt(i.outage_start_time) }, ...(actions ? [{ h: "Actions", f: actions }] : [])], list, "No incidents");
}
function bindIncidentLinks(el) { el.querySelectorAll("[data-view-inc]").forEach(a => a.onclick = e => { e.preventDefault(); incidentModal(a.dataset.viewInc).catch(x => toast(x.message, "error")); }); }

const views = {
  async overview(el) {
    const o = await api("/admin/overview"), s = o.stats;
    el.innerHTML = `<div class="cards">${statCard(t("active_outages", "Active outages"), s.active_outages, `${s.residents_affected_now} residents affected`, true)}
      ${statCard(t("affected_areas", "Affected areas"), s.affected_areas)}${statCard(t("resolved", "Resolved incidents"), s.resolved_incidents)}
      ${statCard(t("avg_restore", "Avg restoration time"), mins(s.avg_restoration_minutes), "resolved incidents in this system")}
      ${statCard(t("total_users", "Total users"), s.total_users, `${s.total_linemen} approved linemen`)}${statCard("Avg rating", s.avg_rating ?? "—", "out of 5")}</div>
      <div class="two"><div class="panel"><h2>Incidents by status</h2><div class="chart-box"><canvas id="c1"></canvas></div></div>
      <div class="panel"><h2>Incidents by area</h2><div class="chart-box"><canvas id="c2"></canvas></div></div></div>
      <div class="panel"><h2>Area-wise statistics</h2>${table([{ h: "Area", f: a => esc(a.area_name) }, { h: "Incidents", f: a => esc(a.incidents) },
        { h: "Active", f: a => esc(a.active ?? 0) }, { h: "Residents affected (total)", f: a => esc(a.total_affected) }], o.areas)}</div>`;
    drawChart("c1", { type: "doughnut", data: { labels: o.status_breakdown.map(x => statusText(x.status)), datasets: [{ data: o.status_breakdown.map(x => x.n), backgroundColor: PALETTE }] } });
    drawChart("c2", { type: "bar", data: { labels: o.areas.map(a => a.area_name), datasets: [{ label: "Incidents", data: o.areas.map(a => a.incidents), backgroundColor: "#1565D8" },
      { label: "Active", data: o.areas.map(a => a.active || 0), backgroundColor: "#64B5F6" }] }, options: { plugins: { legend: { display: true } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } } });
  },
  async users(el) {
    const { users } = await api("/admin/users");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_users">Manage Users</h2>${table([{ h: "Name", f: u => esc(u.full_name) + sampleBadge(u.is_sample) }, { h: "Email", f: u => esc(u.email) },
      { h: "Role", f: u => `<span class="badge">${esc(u.role)}</span>` }, { h: "Area", f: u => esc(u.area_name || "—") }, { h: "Joined", f: u => fmt(u.created_at) },
      { h: "Active", f: u => u.is_active ? '<span class="badge ok">Active</span>' : '<span class="badge bad">Disabled</span>' },
      { h: "", f: u => u.id === me.id ? "" : `<button class="btn btn-outline btn-sm" data-tog="${u.id}" data-to="${u.is_active ? 0 : 1}">${u.is_active ? "Disable" : "Enable"}</button>` }], users)}</div>`;
    el.querySelectorAll("[data-tog]").forEach(b => b.onclick = async () => {
      if (!confirm("Change this account's access?")) return;
      try { await api(`/admin/users/${b.dataset.tog}/active`, { method: "POST", body: { is_active: b.dataset.to === "1" } }); views.users(el); } catch (x) { toast(x.message, "error"); } });
  },
  async linemen(el) {
    await loadRefs();
    el.innerHTML = `<div class="two"><div class="panel"><h2 data-i18n="nav_linemen">Manage Linemen</h2>${table([{ h: "Name", f: l => esc(l.full_name) }, { h: "Code", f: l => esc(l.employee_code) },
      { h: "Area", f: l => esc(l.area_name || "—") }, { h: "Open", f: l => esc(l.open_incidents) },
      { h: "Approval", f: l => `<span class="badge ${l.approval_status === "APPROVED" ? "ok" : "bad"}">${esc(l.approval_status)}</span>` },
      { h: "", f: l => `<button class="btn btn-outline btn-sm" data-ap="${l.id}" data-to="${l.approval_status === "APPROVED" ? "SUSPENDED" : "APPROVED"}">${l.approval_status === "APPROVED" ? "Suspend" : "Approve"}</button>` }], LINEMEN)}</div>
      <div class="panel"><h2>Create lineman account</h2><p class="hint" style="color:var(--muted)">Only administrators can create employee accounts.</p>
      <form id="f"><div class="field"><label for="n">Full name</label><input id="n" required></div><div class="field"><label for="e">Email</label><input id="e" type="email" required></div>
      <div class="field"><label for="p">Phone</label><input id="p"></div><div class="field"><label for="c">Employee code</label><input id="c" required></div>
      <div class="field"><label for="d">Designation</label><input id="d" value="Lineman"></div><div class="field"><label for="a">Area</label><select id="a"><option value="">—</option>${areaOpts()}</select></div>
      <div class="field"><label for="pw">Temporary password</label><input id="pw" type="password" autocomplete="new-password"><span class="hint">8+ characters, letters and digits.</span></div>
      <p class="error-text" id="err"></p><button class="btn btn-primary" data-i18n="create">Create</button></form></div></div>`;
    el.querySelectorAll("[data-ap]").forEach(b => b.onclick = async () => { try { await api(`/admin/linemen/${b.dataset.ap}/approval`, { method: "POST", body: { approval_status: b.dataset.to } }); views.linemen(el); } catch (x) { toast(x.message, "error"); } });
    el.querySelector("#f").onsubmit = async e => { e.preventDefault();
      const g = id => el.querySelector("#" + id).value, body = { full_name: g("n"), email: g("e"), phone: g("p") || undefined, employee_code: g("c"), designation: g("d"), password: g("pw") };
      if (g("a")) body.area_id = +g("a");
      try { await api("/admin/linemen", { method: "POST", body }); toast("Lineman created", "success"); views.linemen(el); applyI18n(el); } catch (x) { el.querySelector("#err").textContent = x.message; } };
  },
  async incidents(el, filter) {
    await loadRefs();
    const status = el.dataset.filter || "ACTIVE";
    const { incidents } = await api("/admin/incidents?limit=200&status=" + status);
    el.innerHTML = `<div class="panel"><div class="toolbar"><h2 style="flex:1;margin:0" data-i18n="nav_incidents">Manage Incidents</h2>
      <div class="field"><label for="flt">Show</label><select id="flt"><option value="ACTIVE">Active</option><option value="RESOLVED">Resolved</option><option value="REPORTED">Reported</option>
      <option value="VERIFIED">Verified</option><option value="ASSIGNED">Assigned</option><option value="REPAIR_IN_PROGRESS">Repair in progress</option></select></div></div>
      ${incidentRows(incidents, i => i.status === "REPORTED" ? `<button class="btn btn-outline btn-sm" data-verify="${i.id}">${esc(t("verify", "Verify"))}</button>` : "")}</div>`;
    el.querySelector("#flt").value = status;
    el.querySelector("#flt").onchange = e => { el.dataset.filter = e.target.value; views.incidents(el); };
    bindIncidentLinks(el);
    el.querySelectorAll("[data-verify]").forEach(b => b.onclick = async () => { try { await api(`/admin/incidents/${b.dataset.verify}/verify`, { method: "POST", body: {} }); toast("Incident verified", "success"); views.incidents(el); applyI18n(el); } catch (x) { toast(x.message, "error"); } });
  },
  async assignments(el) {
    await loadRefs();
    const { incidents } = await api("/admin/incidents?limit=200&status=ACTIVE");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_assignments">Assignments</h2><p class="hint" style="color:var(--muted)">Assigning a Reported incident verifies it first. Reassigning keeps the current status.</p>
      ${LINEMEN.some(l => l.approval_status === "APPROVED") ? incidentRows(incidents, i => `<div style="display:flex;gap:6px"><select data-sel="${i.id}" aria-label="Lineman">${lmOpts()}</select>
        <button class="btn btn-primary btn-sm" data-asg="${i.id}">${esc(t("assign", "Assign"))}</button></div>`) : `<div class="empty">No approved linemen. Create one under Manage Linemen.</div>`}</div>`;
    bindIncidentLinks(el);
    el.querySelectorAll("[data-asg]").forEach(b => b.onclick = async () => {
      const lid = +el.querySelector(`[data-sel="${b.dataset.asg}"]`).value;
      try { await api(`/admin/incidents/${b.dataset.asg}/assign`, { method: "POST", body: { lineman_id: lid } }); toast("Incident assigned; residents notified", "success"); views.assignments(el); applyI18n(el); } catch (x) { toast(x.message, "error"); } });
  },
  async analytics(el) {
    const a = await api("/admin/analytics");
    const reports = await api("/admin/reports?limit=20");
    el.innerHTML = `<div class="notice" style="margin-bottom:18px"><b>Data notice:</b> ${esc(a.data_notice)}<br>
      Restoration model: trained on <b>${esc(a.model.data_source)}</b> (${esc(a.model.n_rows)} rows); hold-out error ≈ ${esc(a.model.mae_minutes)} min (naive baseline ${esc(a.model.baseline_mae_minutes)} min). Predictions are estimates only.</div>
      <div class="cards">${statCard("Records analysed", a.n_records, "", true)}${statCard("Overall avg duration", mins(a.overall_avg_minutes))}
      ${statCard("Duplicate reports linked", reports.duplicates_prevented, "reports grouped into existing incidents")}</div>
      <div class="two"><div class="panel"><h2>Outage frequency by area</h2><div class="chart-box"><canvas id="a1"></canvas></div></div>
      <div class="panel"><h2>Average duration by area (min)</h2><div class="chart-box"><canvas id="a2"></canvas></div></div>
      <div class="panel"><h2>Outages by hour of day</h2><div class="chart-box"><canvas id="a3"></canvas></div></div>
      <div class="panel"><h2>Category mix</h2><div class="chart-box"><canvas id="a4"></canvas></div></div></div>
      <div class="two"><div class="panel"><h2>Repeated outage patterns</h2>${table([{ h: "Area", f: r => esc(r.area) }, { h: "Outages", f: r => esc(r.outages) }, { h: "Median gap (days)", f: r => esc(r.median_gap_days) },
        { h: "Typical hour", f: r => esc(r.common_hour + ":00") }, { h: "Common type", f: r => esc(catText(r.common_category)) }], a.repeated_patterns)}</div>
      <div class="panel"><h2>Unusual outage activity</h2>${table([{ h: "Area", f: r => esc(r.area) }, { h: "Date", f: r => esc(r.date) }, { h: "Outages", f: r => esc(r.outages) },
        { h: "Score", f: r => `<span class="badge warn">${esc(r.score)}</span>` }], a.anomalies, "No unusual days detected")}
        <p class="hint" style="color:var(--muted)">Flags days with far more outages than the area's normal (robust z-score ≥ 3.5).</p></div></div>
      <div class="panel"><div class="toolbar"><h2 style="flex:1;margin:0">Complaint reports</h2><a class="btn btn-outline btn-sm" href="#" id="csv">Download CSV</a></div>
      ${table([{ h: "Report", f: r => esc(r.report_code) }, { h: "Resident", f: r => esc(r.full_name) }, { h: "Area", f: r => esc(r.area_name) }, { h: "Incident", f: r => esc(r.incident_code) },
        { h: "Linked", f: r => r.matched_existing ? '<span class="badge">Linked to existing</span>' : "New incident" }, { h: "When", f: r => fmt(r.created_at) }], reports.reports)}</div>`;
    drawChart("a1", { type: "bar", data: { labels: a.frequent_areas.map(x => x.area), datasets: [{ label: "Outages", data: a.frequent_areas.map(x => x.outages), backgroundColor: "#1565D8" }] }, options: { indexAxis: "y" } });
    drawChart("a2", { type: "bar", data: { labels: a.avg_duration_by_area.map(x => x.area), datasets: [{ label: "Minutes", data: a.avg_duration_by_area.map(x => x.avg_minutes), backgroundColor: "#64B5F6" }] } });
    drawChart("a3", { type: "line", data: { labels: [...Array(24).keys()], datasets: [{ label: "Outages", data: a.hourly_distribution, borderColor: "#1565D8", backgroundColor: "rgba(100,181,246,.3)", fill: true, tension: .3 }] } });
    drawChart("a4", { type: "doughnut", data: { labels: a.category_mix.map(x => catText(x.category)), datasets: [{ data: a.category_mix.map(x => x.outages), backgroundColor: PALETTE.concat(["#BBD9FA"]) }] } });
    el.querySelector("#csv").onclick = async e => { e.preventDefault();
      const res = await fetch(API + "/admin/reports.csv", { headers: { Authorization: "Bearer " + Auth.token() } });
      const url = URL.createObjectURL(await res.blob()); const x = document.createElement("a"); x.href = url; x.download = "urjasense_reports.csv"; x.click(); URL.revokeObjectURL(url); };
  },
  async areas(el) {
    await loadRefs();
    el.innerHTML = `<div class="two"><div class="panel"><h2 data-i18n="nav_areas">Areas and Locations</h2>${table([{ h: "Name", f: a => esc(a.name) }, { h: "Ward", f: a => esc(a.ward_code) },
      { h: "Centre", f: a => esc(a.latitude + ", " + a.longitude) }, { h: "Radius", f: a => esc(a.radius_km) + " km" },
      { h: "Active", f: a => a.is_active ? '<span class="badge ok">Yes</span>' : '<span class="badge bad">No</span>' },
      { h: "", f: a => `<button class="btn btn-outline btn-sm" data-edit="${a.id}">Edit</button>` }], AREAS)}</div>
      <div class="panel"><h2 id="ft">Add area</h2><form id="f"><input type="hidden" id="id">
      <div class="field"><label for="n">Name</label><input id="n" required></div><div class="row"><div class="field"><label for="c">City</label><input id="c" value="Bhopal"></div><div class="field"><label for="d">District</label><input id="d" value="Bhopal"></div></div>
      <div class="field"><label for="w">Ward code</label><input id="w" required></div><div class="row"><div class="field"><label for="la">Latitude</label><input id="la" required inputmode="decimal"></div><div class="field"><label for="lo">Longitude</label><input id="lo" required inputmode="decimal"></div></div>
      <div class="field"><label for="r">Radius (km)</label><input id="r" value="1.5" inputmode="decimal"></div><div class="field"><label><input type="checkbox" id="act" checked style="width:auto;min-height:0"> Active</label></div>
      <p class="error-text" id="err"></p><button class="btn btn-primary" data-i18n="save">Save</button></form></div></div>`;
    el.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => { const a = AREAS.find(x => x.id === +b.dataset.edit);
      el.querySelector("#ft").textContent = "Edit area"; const s = (id, v) => el.querySelector("#" + id).value = v;
      s("id", a.id); s("n", a.name); s("c", a.city); s("d", a.district); s("w", a.ward_code); s("la", a.latitude); s("lo", a.longitude); s("r", a.radius_km); el.querySelector("#act").checked = !!a.is_active; });
    el.querySelector("#f").onsubmit = async e => { e.preventDefault(); const g = id => el.querySelector("#" + id).value;
      const body = { name: g("n"), city: g("c"), district: g("d"), ward_code: g("w"), latitude: g("la"), longitude: g("lo"), radius_km: g("r"), is_active: el.querySelector("#act").checked };
      try { g("id") ? await api("/admin/areas/" + g("id"), { method: "PUT", body }) : await api("/admin/areas", { method: "POST", body }); toast("Area saved", "success"); views.areas(el); applyI18n(el); } catch (x) { el.querySelector("#err").textContent = x.message; } };
  },
  async feedback(el) {
    const f = await api("/admin/feedback");
    el.innerHTML = `<div class="cards">${statCard("Average rating", f.average ?? "—", "out of 5", true)}${statCard("Responses", f.feedback.length)}</div>
      <div class="panel"><h2 data-i18n="nav_feedback">Feedback</h2>${table([{ h: "Incident", f: r => esc(r.incident_code) }, { h: "Area", f: r => esc(r.area_name) }, { h: "Resident", f: r => esc(r.full_name) },
        { h: "Rating", f: r => "★".repeat(r.rating) + "☆".repeat(5 - r.rating) }, { h: "Feedback", f: r => esc(r.feedback || "—") }, { h: "Date", f: r => fmt(r.created_at) }], f.feedback, "No feedback yet")}</div>`;
  },
  async broadcast(el) {
    await loadRefs();
    const { notifications } = await api("/admin/notifications");
    el.innerHTML = `<div class="two"><div class="panel"><h2>Send announcement</h2><p class="hint" style="color:var(--muted)">Delivered as in-app notifications to active residents. Amazon SNS delivery is optional and disabled unless configured.</p>
      <form id="f"><div class="field"><label for="a">Audience</label><select id="a"><option value="">All residents</option>${areaOpts()}</select></div>
      <div class="field"><label for="t">Title</label><input id="t" required maxlength="200"></div><div class="field"><label for="m">Message</label><textarea id="m" required maxlength="1000"></textarea></div>
      <div class="field"><label for="th">Title (Hindi, optional)</label><input id="th" maxlength="300"></div><div class="field"><label for="mh">Message (Hindi, optional)</label><textarea id="mh" maxlength="1000"></textarea></div>
      <p class="error-text" id="err"></p><button class="btn btn-primary">Send</button></form></div>
      <div class="panel"><h2 data-i18n="nav_broadcast">Recent notifications</h2>${table([{ h: "To", f: n => esc(n.full_name) }, { h: "Title", f: n => esc(n.title) }, { h: "Read", f: n => n.is_read ? "Yes" : "No" }, { h: "Sent", f: n => fmt(n.created_at) }], notifications)}</div></div>`;
    el.querySelector("#f").onsubmit = async e => { e.preventDefault(); const g = id => el.querySelector("#" + id).value;
      if (!confirm("Send this announcement?")) return;
      try { const r = await api("/admin/notifications/broadcast", { method: "POST", body: { title: g("t"), message: g("m"), title_hi: g("th"), message_hi: g("mh"), ...(g("a") ? { area_id: +g("a") } : {}) } });
        toast(`Sent to ${r.sent} residents`, "success"); views.broadcast(el); applyI18n(el); } catch (x) { el.querySelector("#err").textContent = x.message; } };
  },
  async logs(el) {
    const { logs } = await api("/admin/logs?limit=200");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_logs">System Logs</h2>${table([{ h: "Time", f: l => fmt(l.created_at) }, { h: "User", f: l => esc(l.full_name || "—") }, { h: "Action", f: l => `<span class="badge">${esc(l.action)}</span>` },
      { h: "Entity", f: l => esc((l.entity_type || "") + (l.entity_id ? " #" + l.entity_id : "")) }, { h: "Details", f: l => esc(l.details || "") }, { h: "IP", f: l => esc(l.ip_address || "") }], logs)}</div>`;
  },
};
const router = makeRouter(views, "overview");
langSelect(() => router.go(router.current()));
applyI18n();
router.go(location.hash.slice(1) || "overview");
