/* Login + registration pages */
(async function () {
  applyI18n(); langSelect(() => {});
  const areaSel = document.getElementById("area_id");
  if (areaSel) {
    try { const { areas } = await api("/areas", { auth: false });
      areaSel.innerHTML = `<option value="">—</option>` + areas.map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join(""); } catch {}
  }
  const form = document.getElementById("auth-form"); if (!form) return;
  const isRegister = form.dataset.mode === "register";
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const err = document.getElementById("form-error"); err.textContent = "";
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    const data = Object.fromEntries(new FormData(form));
    if (isRegister) { data.preferred_language = Lang.get(); if (!data.area_id) delete data.area_id; else data.area_id = +data.area_id; }
    try {
      const res = await api(isRegister ? "/auth/register" : "/auth/login", { method: "POST", body: data, auth: false });
      Auth.save(res.token, res.user);
      if (res.user.preferred_language && !isRegister) Lang.set(res.user.preferred_language);
      location.href = "dashboards/" + Auth.home(res.user.role);
    } catch (ex) { err.textContent = ex.message; btn.disabled = false; }
  });
  document.querySelectorAll("[data-demo]").forEach(b => b.addEventListener("click", () => {
    form.email.value = b.dataset.demo; form.password.value = "Demo@1234"; }));
})();
