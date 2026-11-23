/* Resident dashboard */
const me = Auth.guard("public");
let AREAS = [];
setupShell();
document.getElementById("userchip").textContent = me ? me.full_name : "";

async function areas() { if (!AREAS.length) AREAS = (await api("/areas", { auth: false })).areas; return AREAS; }

async function showIncident(id, byCode) {
  const r = byCode ? await api("/incidents/track?code=" + encodeURIComponent(id), { auth: false }) : await api("/user/incidents/" + id);
  const i = r.incident;
  openModal(i.incident_code, `
    <div style="display:flex;gap:8px;flex-wrap:wrap">${statusBadge(i.status)} ${priorityBadge(i.priority)}${sampleBadge(i.is_sample)}</div>
    ${stepper(i.status)}
    <div class="kv">
      <div><b>${esc(t("area", "Area"))}</b>${esc(i.area_name)}</div>
      <div><b>${esc(t("affected", "Residents affected"))}</b>${esc(i.affected_count)}</div>
      <div><b>Outage started</b>${fmt(i.outage_start_time)}</div>
      <div><b>${esc(t("suggested_cat", "Suggested category (automatic, not verified)"))}</b>${esc(catText(i.verified_category || i.suggested_category))}
        ${i.category_is_verified ? '<span class="badge ok">Verified</span>' : '<span class="badge est">Unverified</span>'}</div>
      <div><b>${esc(t("official_cause", "Verified cause"))}</b>${i.official_cause ? esc(i.official_cause) : "Not yet confirmed by the department"}</div>
      ${estimateHtml(i)}
    </div>
    <h3>Updates</h3>${timeline(r.updates)}`);
}

const views = {
  async overview(el) {
    const o = await api("/user/overview");
    el.innerHTML = `
      <div class="cards">
        ${statCard(t("my_reports", "My reports"), o.my_reports, `${o.my_active} active`, true)}
        ${statCard(t("active_my_area", "Active in my area"), o.active_in_my_area)}
        ${statCard(t("active_citywide", "Active citywide"), o.active_citywide)}
        ${statCard(t("unread", "Unread notifications"), o.unread_notifications)}
      </div>
      <div class="two">
        <div class="panel"><h2 data-i18n="track_incident">Track an incident</h2>
          <form id="track-form" class="toolbar"><div class="field" style="flex:1"><label for="code" data-i18n="code">Report or incident code</label>
            <input id="code" placeholder="INC-20261122-0001 / RPT-…" required></div>
            <button class="btn btn-primary" data-i18n="track">Track</button></form>
          <a class="btn btn-light" href="#report" id="go-report" data-i18n="nav_report">Report Power Outage</a></div>
        <div class="panel"><h2 data-i18n="recent_updates">Recent updates on my incidents</h2>
          ${o.recent_updates.length ? `<ul class="timeline">${o.recent_updates.map(u => `<li><b>${esc(u.incident_code)} · ${esc(statusText(u.new_status))}</b>
            <small>${esc(u.area_name)} · ${fmt(u.created_at)}</small>${u.remarks ? `<div>${esc(u.remarks)}</div>` : ""}</li>`).join("")}</ul>`
            : `<div class="empty">Nothing yet. Report an outage to start tracking.</div>`}</div>
      </div>`;
    el.querySelector("#track-form").onsubmit = async e => { e.preventDefault();
      try { await showIncident(el.querySelector("#code").value.trim(), true); } catch (x) { toast(x.message, "error"); } };
    el.querySelector("#go-report").onclick = e => { e.preventDefault(); router.go("report"); };
  },

  async report(el) {
    const list = await areas();
    const d = new Date(Date.now() - 15 * 60000); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    el.innerHTML = `<div class="two"><div class="panel"><h2 data-i18n="nav_report">Report Power Outage</h2>
      <form id="rep" novalidate>
        <div class="field"><label for="area_id" data-i18n="area">Area</label><select id="area_id" required>
          ${list.map(a => `<option value="${a.id}" ${a.id === me.area_id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div>
        <div class="field"><label for="location_text" data-i18n="location">Location / address</label><input id="location_text" required maxlength="255" placeholder="e.g. Block C, near the park"></div>
        <div class="field"><label for="start" data-i18n="outage_start">When did the power go out?</label><input id="start" type="datetime-local" value="${d.toISOString().slice(0, 16)}" required></div>
        <div class="field"><label for="details" data-i18n="issue_details">Issue details</label><textarea id="details" maxlength="1000" placeholder="e.g. loud bang from the transformer, sparks, tree fell on wire…"></textarea>
          <span class="hint" id="cat-hint"></span></div>
        <div class="field"><label><input type="checkbox" id="gps" style="width:auto;min-height:0"> <span data-i18n="use_gps">Share my GPS location (optional)</span></label><span class="hint" id="gps-hint"></span></div>
        <p class="error-text" id="err" role="alert"></p>
        <button class="btn btn-primary" data-i18n="submit_report">Submit report</button>
      </form></div>
      <div class="panel" id="result"><h2>What happens next</h2>
        <p>If someone nearby already reported the same outage, your report is <b>linked to the existing incident</b> — you still get your own report ID and updates.</p>
        <p class="hint" style="color:var(--muted)">Restoration times are model estimates, not commitments. Only authorised employees can confirm the cause.</p></div></div>`;
    let coords = null;
    const gps = el.querySelector("#gps");
    gps.onchange = () => {
      if (!gps.checked) { coords = null; el.querySelector("#gps-hint").textContent = ""; return; }
      if (!navigator.geolocation) { el.querySelector("#gps-hint").textContent = "GPS not available on this device."; gps.checked = false; return; }
      navigator.geolocation.getCurrentPosition(p => { coords = { latitude: +p.coords.latitude.toFixed(6), longitude: +p.coords.longitude.toFixed(6) };
        el.querySelector("#gps-hint").textContent = `Location captured (${coords.latitude}, ${coords.longitude})`; },
        () => { el.querySelector("#gps-hint").textContent = "Could not get location. You can still submit without it."; gps.checked = false; });
    };
    let timer;
    el.querySelector("#details").oninput = e => { clearTimeout(timer); timer = setTimeout(async () => {
      if (!e.target.value.trim()) { el.querySelector("#cat-hint").textContent = ""; return; }
      try { const s = await api("/user/reports/suggest-category", { method: "POST", body: { issue_details: e.target.value } });
        el.querySelector("#cat-hint").textContent = `${t("suggested_cat", "Suggested category (automatic, not verified)")}: ${catText(s.category)}`; } catch {} }, 400); };
    el.querySelector("#rep").onsubmit = async e => {
      e.preventDefault(); const err = el.querySelector("#err"); err.textContent = "";
      const btn = e.target.querySelector("button"); btn.disabled = true;
      try {
        const r = await api("/user/reports", { method: "POST", body: { area_id: +el.querySelector("#area_id").value,
          location_text: el.querySelector("#location_text").value, outage_start_time: el.querySelector("#start").value,
          issue_details: el.querySelector("#details").value, ...(coords || {}) } });
        const i = r.incident;
        el.querySelector("#result").innerHTML = `<h2>${r.linked_to_existing ? esc(t("linked_existing", "Linked to an existing incident")) : esc(t("new_incident", "New incident created"))}</h2>
          ${r.already_reported ? `<p class="badge warn">You had already reported this outage</p>` : ""}
          <div class="kv"><div><b>Your report ID</b><big>${esc(r.report_code)}</big></div><div><b>Incident ID</b><big>${esc(i.incident_code)}</big></div>
          <div><b>${esc(t("status", "Status"))}</b>${statusBadge(i.status)}</div><div><b>${esc(t("affected", "Residents affected"))}</b>${esc(i.affected_count)}</div>
          ${estimateHtml(i)}</div>
          <button class="btn btn-outline" id="view-inc">View incident</button>`;
        el.querySelector("#view-inc").onclick = () => showIncident(i.id);
        toast(r.linked_to_existing ? t("linked_existing", "Linked to an existing incident") : t("new_incident", "New incident created"), "success");
      } catch (x) { err.textContent = x.message; } finally { btn.disabled = false; }
    };
  },

  async map(el) {
    const [{ incidents }, list] = await Promise.all([api("/incidents/active", { auth: false }), areas()]);
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_map">Live Outage Map</h2>
      <div id="map" role="application" aria-label="Outage map"></div>
      <p class="hint" style="color:var(--muted)">Marker colour = priority (red high/critical, amber medium, blue low). Incidents without GPS are placed at the centre of their area.</p></div>
      <div class="panel"><h2>Active incidents (${incidents.length})</h2>${table([
        { h: "Incident", f: i => `<a href="#" data-inc="${i.id}">${esc(i.incident_code)}</a>${sampleBadge(i.is_sample)}` },
        { h: t("area", "Area"), f: i => esc(i.area_name) }, { h: t("status", "Status"), f: i => statusBadge(i.status) },
        { h: t("priority", "Priority"), f: i => priorityBadge(i.priority) }, { h: t("affected", "Affected"), f: i => esc(i.affected_count) },
        { h: t("est_restore", "Est. restoration"), f: i => (i.lineman_eta_at ? fmt(i.lineman_eta_at) + " ✓" : fmt(i.predicted_restoration_at) + " (est.)") }], incidents, "No active outages right now")}</div>`;
    el.querySelectorAll("[data-inc]").forEach(a => a.onclick = e => { e.preventDefault(); showIncident(a.dataset.inc, false).catch(x => toast(x.message, "error")); });
    if (typeof L === "undefined") { el.querySelector("#map").innerHTML = `<div class="empty">Map library failed to load. The list below still works.</div>`; return; }
    const map = L.map("map").setView([23.2300, 77.4200], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
    const byId = Object.fromEntries(list.map(a => [a.id, a]));
    list.forEach(a => L.circle([a.latitude, a.longitude], { radius: a.radius_km * 1000, color: "#64B5F6", weight: 1, fillOpacity: .06 }).addTo(map));
    const group = [];
    incidents.forEach(i => {
      const a = byId[i.area_id]; const lat = i.latitude ?? a?.latitude, lng = i.longitude ?? a?.longitude; if (lat == null) return;
      const color = ["HIGH", "CRITICAL"].includes(i.priority) ? "#C62828" : i.priority === "MEDIUM" ? "#B7791F" : "#1565D8";
      const m = L.circleMarker([lat, lng], { radius: 9 + Math.min(i.affected_count, 20) / 2, color, fillColor: color, fillOpacity: .55, weight: 2 }).addTo(map);
      m.bindPopup(`<b>${esc(i.incident_code)}</b><br>${esc(i.area_name)}<br>${esc(statusText(i.status))} · ${esc(i.affected_count)} affected`);
      group.push([lat, lng]);
    });
    if (group.length) map.fitBounds(group, { maxZoom: 14, padding: [30, 30] });
  },

  async myreports(el) {
    const { reports } = await api("/user/reports");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_myreports">My Reports</h2>${table([
      { h: "Report ID", f: r => esc(r.report_code) },
      { h: "Incident", f: r => `<a href="#" data-inc="${r.incident_id}">${esc(r.incident_code)}</a>${r.matched_existing ? ' <span class="badge">Linked</span>' : ""}` },
      { h: t("area", "Area"), f: r => esc(r.area_name) }, { h: "Location", f: r => esc(r.location_text) },
      { h: t("status", "Status"), f: r => statusBadge(r.status) }, { h: t("affected", "Affected"), f: r => esc(r.affected_count) },
      { h: "Reported", f: r => fmt(r.created_at) }], reports, "You have not reported any outage yet")}</div>`;
    el.querySelectorAll("[data-inc]").forEach(a => a.onclick = e => { e.preventDefault(); showIncident(a.dataset.inc).catch(x => toast(x.message, "error")); });
  },

  async notifications(el) {
    const { notifications: n } = await api("/user/notifications");
    const hi = Lang.get() === "hi";
    el.innerHTML = `<div class="panel"><div class="toolbar"><h2 style="flex:1;margin:0" data-i18n="nav_notifications">Notifications</h2>
      <button class="btn btn-outline btn-sm" id="readall" data-i18n="mark_all_read">Mark all read</button></div>
      ${n.length ? n.map(x => `<div class="incident-card" style="${x.is_read ? "" : "border-left:5px solid var(--blue)"}"><header><b>${esc(hi && x.title_hi ? x.title_hi : x.title)}</b>
        <small>${fmt(x.created_at)}</small></header><div>${esc(hi && x.message_hi ? x.message_hi : x.message)}</div></div>`).join("") : `<div class="empty">No notifications</div>`}</div>`;
    el.querySelector("#readall").onclick = async () => { await api("/user/notifications/read-all", { method: "POST", body: {} }); views.notifications(el); applyI18n(el); };
  },

  async history(el) {
    const { history: h } = await api("/user/history");
    el.innerHTML = `<div class="panel"><h2 data-i18n="nav_history">Outage History</h2>${table([
      { h: "Incident", f: r => `<a href="#" data-inc="${r.id}">${esc(r.incident_code)}</a>${r.reported_by_me ? ' <span class="badge">Mine</span>' : ""}` },
      { h: t("area", "Area"), f: r => esc(r.area_name) }, { h: "Started", f: r => fmt(r.outage_start_time) },
      { h: "Resolved", f: r => fmt(r.resolved_at) },
      { h: "Duration", f: r => mins(r.resolved_at ? (new Date(r.resolved_at) - new Date(r.outage_start_time)) / 60000 : null) },
      { h: t("official_cause", "Verified cause"), f: r => esc(r.official_cause || "—") }], h, "No resolved incidents yet")}</div>`;
    el.querySelectorAll("[data-inc]").forEach(a => a.onclick = e => { e.preventDefault(); showIncident(a.dataset.inc).catch(x => toast(x.message, "error")); });
  },

  async feedback(el) {
    const [{ incidents }, { ratings }] = await Promise.all([api("/user/rateable"), api("/user/ratings")]);
    el.innerHTML = `<div class="two"><div class="panel"><h2 data-i18n="rate_resolved">Rate a resolved incident</h2>
      ${incidents.length ? `<form id="rate"><div class="field"><label for="inc">Incident</label><select id="inc">${incidents.map(i => `<option value="${i.id}">${esc(i.incident_code)} — ${esc(i.area_name)}</option>`).join("")}</select></div>
        <div class="field"><label data-i18n="rating">Rating</label><div class="stars" id="stars">${[1, 2, 3, 4, 5].map(n => `<button type="button" data-n="${n}" aria-label="${n} stars">★</button>`).join("")}</div></div>
        <div class="field"><label for="fb" data-i18n="feedback">Feedback</label><textarea id="fb" maxlength="1000"></textarea></div>
        <p class="error-text" id="err"></p><button class="btn btn-primary" data-i18n="submit">Submit</button></form>`
        : `<div class="empty">No resolved incidents are waiting for your rating.</div>`}</div>
      <div class="panel"><h2>My ratings</h2>${table([{ h: "Incident", f: r => esc(r.incident_code) }, { h: "Rating", f: r => "★".repeat(r.rating) },
        { h: "Feedback", f: r => esc(r.feedback || "") }, { h: "Date", f: r => fmt(r.created_at) }], ratings, "No ratings yet")}</div></div>`;
    let val = 0; const stars = el.querySelectorAll("#stars button");
    stars.forEach(b => b.onclick = () => { val = +b.dataset.n; stars.forEach(s => s.classList.toggle("on", +s.dataset.n <= val)); });
    el.querySelector("#rate")?.addEventListener("submit", async e => { e.preventDefault();
      if (!val) { el.querySelector("#err").textContent = "Please choose a rating"; return; }
      try { await api("/user/ratings", { method: "POST", body: { incident_id: +el.querySelector("#inc").value, rating: val, feedback: el.querySelector("#fb").value } });
        toast("Thank you for your feedback", "success"); views.feedback(el); applyI18n(el); } catch (x) { el.querySelector("#err").textContent = x.message; } });
  },

  async profile(el) {
    const list = await areas();
    const { user: u } = await api("/auth/me");
    el.innerHTML = `<div class="two"><div class="panel"><h2 data-i18n="nav_profile">Profile and Settings</h2>
      <form id="prof"><div class="field"><label for="n" data-i18n="full_name">Full name</label><input id="n" value="${esc(u.full_name)}"></div>
      <div class="field"><label for="p" data-i18n="phone">Phone</label><input id="p" inputmode="numeric"></div>
      <div class="field"><label for="a" data-i18n="area">Area</label><select id="a"><option value="">—</option>${list.map(a => `<option value="${a.id}" ${a.id === u.area_id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div>
      <div class="field"><label for="l" data-i18n="language">Language</label><select id="l">${Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${k === Lang.get() ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <p class="error-text" id="err"></p><button class="btn btn-primary" data-i18n="save">Save</button></form></div>
      <div class="panel"><h2>Change password</h2><form id="pw"><div class="field"><label for="cp">Current password</label><input id="cp" type="password" autocomplete="current-password"></div>
      <div class="field"><label for="np">New password</label><input id="np" type="password" autocomplete="new-password"></div><p class="error-text" id="err2"></p>
      <button class="btn btn-outline">Update password</button></form></div></div>`;
    el.querySelector("#prof").onsubmit = async e => { e.preventDefault();
      const body = { full_name: el.querySelector("#n").value, preferred_language: el.querySelector("#l").value };
      if (el.querySelector("#p").value) body.phone = el.querySelector("#p").value;
      if (el.querySelector("#a").value) body.area_id = +el.querySelector("#a").value;
      try { const r = await api("/auth/me", { method: "PUT", body }); Lang.set(body.preferred_language);
        document.querySelector(".lang-select").value = body.preferred_language;
        Auth.save(Auth.token(), { ...me, full_name: r.user.full_name, preferred_language: r.user.preferred_language, area_id: r.user.area_id });
        applyI18n(); toast(t("lang_saved", "Profile saved"), "success"); router.go("profile"); } catch (x) { el.querySelector("#err").textContent = x.message; } };
    el.querySelector("#pw").onsubmit = async e => { e.preventDefault();
      try { await api("/auth/change-password", { method: "POST", body: { current_password: el.querySelector("#cp").value, new_password: el.querySelector("#np").value } });
        toast("Password updated", "success"); e.target.reset(); } catch (x) { el.querySelector("#err2").textContent = x.message; } };
  },
};

const router = makeRouter(views, "overview");
langSelect(() => router.go(router.current()));
applyI18n();
router.go(location.hash.slice(1) || "overview");
