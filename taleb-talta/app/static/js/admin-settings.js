/* Settings tree + field/dashboard/theme/menu builders. */
(function () {
  "use strict";
  var fields = [], menus = [], presets = [], defaultBlocks = [];
  function showErr(form, msg) { var e = form.querySelector(".form-error"); e.textContent = msg; e.hidden = false; }
  function formData(f) { var o = {}; new FormData(f).forEach(function (v, k) { o[k] = v; }); return o; }

  async function loadGeneral() {
    var out = await TT.api("/api/admin/settings", "GET");
    if (!out.success) return;
    var f = document.getElementById("general-form");
    Object.keys(out.data.values).forEach(function (k) {
      var el = f.elements[k]; if (!el) return;
      if (el.type === "checkbox") el.checked = out.data.values[k] === "1"; else el.value = out.data.values[k];
    });
  }
  async function loadFields() {
    var a = await TT.api("/api/custom-fields/user?all=1", "GET");
    var b = await TT.api("/api/custom-fields/course?all=1", "GET");
    fields = (a.success ? a.data : []).concat(b.success ? b.data : []);
    document.getElementById("fields-body").innerHTML = fields.map(function (f) {
      return '<tr><td>' + TT.esc(f.label) + '<br><code dir="ltr">' + TT.esc(f.machine_name) + '</code></td><td>' + TT.esc(TT.t("customfield.entity_" + f.applies_to)) + '</td><td>' + TT.esc(TT.t("customfield." + f.field_type)) + '</td><td>' + TT.esc(TT.t(f.required ? "misc.yes" : "misc.no")) + '</td><td>' + TT.esc(TT.t(f.enabled ? "misc.enabled" : "misc.disabled")) + '</td><td><button class="btn btn-ghost btn-sm" data-edit-field="' + f.id + '">' + TT.esc(TT.t("nav.edit")) + '</button></td></tr>';
    }).join("");
    document.querySelectorAll("[data-edit-field]").forEach(function (b) { b.addEventListener("click", function () { openField(fields.find(function (f) { return f.id === parseInt(b.getAttribute("data-edit-field"), 10); })); }); });
  }
  function openField(f) {
    var form = document.getElementById("field-form"); form.reset();
    form.elements.id.value = f ? f.id : "";
    form.elements.enabled.checked = f ? f.enabled : true;
    form.elements.required.checked = f ? f.required : false;
    if (f) {
      form.elements.label.value = f.label; form.elements.applies_to.value = f.applies_to;
      form.elements.machine_name.value = f.machine_name; form.elements.field_type.value = f.field_type;
      form.elements.options.value = f.options.join("\n"); form.elements.sort_order.value = f.sort_order;
    }
    form.elements.applies_to.disabled = !!f; form.elements.machine_name.disabled = !!f; form.elements.field_type.disabled = !!f;
    document.getElementById("field-options-wrap").hidden = !f || f.field_type !== "select";
    document.getElementById("field-dialog-title").textContent = TT.t(f ? "customfield.edit" : "customfield.add");
    form.querySelector(".form-error").hidden = true;
    document.getElementById("field-dialog").showModal();
  }
  function drawDefaults() {
    var list = document.getElementById("default-block-list");
    list.innerHTML = defaultBlocks.map(function (b, i) {
      return '<div class="builder-row" data-key="' + TT.esc(b.key) + '"><label class="check-row"><input type="checkbox" data-default-enabled ' + (b.enabled ? "checked" : "") + '> ' + TT.esc(TT.t("dashboard.block_" + b.key)) + '</label><span class="actions"><button type="button" class="btn btn-ghost btn-sm" data-default-move="-1" ' + (i === 0 ? "disabled" : "") + '>' + TT.esc(TT.t("misc.up")) + '</button><button type="button" class="btn btn-ghost btn-sm" data-default-move="1" ' + (i === defaultBlocks.length - 1 ? "disabled" : "") + '>' + TT.esc(TT.t("misc.down")) + '</button></span></div>';
    }).join("");
    list.querySelectorAll("[data-default-move]").forEach(function (btn) { btn.addEventListener("click", function () {
      var key = btn.closest(".builder-row").getAttribute("data-key");
      var i = defaultBlocks.findIndex(function (b) { return b.key === key; });
      var j = i + parseInt(btn.getAttribute("data-default-move"), 10);
      var tmp = defaultBlocks[i]; defaultBlocks[i] = defaultBlocks[j]; defaultBlocks[j] = tmp;
      defaultBlocks.forEach(function (b, n) { b.order = n; }); drawDefaults();
    }); });
    list.querySelectorAll("[data-default-enabled]").forEach(function (cb) { cb.addEventListener("change", function () {
      defaultBlocks.find(function (b) { return b.key === cb.closest(".builder-row").getAttribute("data-key"); }).enabled = cb.checked;
    }); });
  }
  async function loadDefaults() {
    var role = document.getElementById("dashboard-role").value;
    var out = await TT.api("/api/admin/dashboard/defaults/" + role, "GET");
    if (out.success) { defaultBlocks = out.data; drawDefaults(); }
  }
  async function loadThemes() {
    var out = await TT.api("/api/themes", "GET");
    if (!out.success) return;
    presets = out.data.presets;
    var baseHtml = ["light", "neutral", "sky"].map(function (k) {
      return '<div class="builder-row"><span>' + TT.esc(TT.t("theme." + k)) + '</span><button class="btn btn-ghost btn-sm" data-activate-theme="' + k + '">' + TT.esc(TT.t("theme.activate")) + '</button></div>';
    }).join("");
    document.getElementById("theme-list").innerHTML = baseHtml + (presets.length ? presets.map(function (p) {
      return '<div class="builder-row"><span><i class="swatch" data-color="' + TT.esc(p.primary) + '"></i> ' + TT.esc(p.name) + '</span><span class="actions"><button class="btn btn-ghost btn-sm" data-activate-theme="' + TT.esc(p.key) + '">' + TT.esc(TT.t("theme.activate")) + '</button><button class="btn btn-danger btn-sm" data-delete-theme="' + p.id + '">' + TT.esc(TT.t("nav.delete")) + '</button></span></div>';
    }).join("") : '<p class="muted">' + TT.esc(TT.t("theme.none")) + '</p>');
    document.querySelectorAll(".swatch").forEach(function (el) { el.style.background = el.getAttribute("data-color"); });
    var select = document.getElementById("role-theme-key");
    select.innerHTML = ["light", "neutral", "sky"].map(function (k) { return '<option value="' + k + '">' + TT.esc(TT.t("theme." + k)) + '</option>'; }).join("") + presets.map(function (p) { return '<option value="' + TT.esc(p.key) + '">' + TT.esc(p.name) + '</option>'; }).join("");
    document.querySelectorAll("[data-activate-theme]").forEach(function (b) { b.addEventListener("click", async function () {
      var res = await TT.api("/api/admin/themes/activate", "POST", { theme_key: b.getAttribute("data-activate-theme") });
      TT.toast(res.message, res.success ? "success" : "error");
    }); });
    document.querySelectorAll("[data-delete-theme]").forEach(function (b) { b.addEventListener("click", async function () {
      if (!window.confirm(TT.t("theme.delete_confirm"))) return;
      var res = await TT.api("/api/admin/themes/" + b.getAttribute("data-delete-theme"), "DELETE");
      TT.toast(res.message, res.success ? "success" : "error"); if (res.success) loadThemes();
    }); });
  }
  async function loadMenus() {
    var out = await TT.api("/api/admin/menus", "GET");
    if (!out.success) return;
    menus = out.data;
    document.getElementById("menus-body").innerHTML = menus.map(function (m) {
      return '<tr><td>' + TT.esc(m.label) + '</td><td dir="ltr">' + TT.esc(m.url) + '</td><td>' + TT.esc(m.role ? TT.t("role." + m.role) : TT.t("misc.all")) + '</td><td>' + m.order + '</td><td>' + TT.esc(TT.t(m.enabled ? "misc.enabled" : "misc.disabled")) + '</td><td>' + (m.editable ? '<button class="btn btn-ghost btn-sm" data-edit-menu="' + m.id + '">' + TT.esc(TT.t("nav.edit")) + '</button> <button class="btn btn-danger btn-sm" data-delete-menu="' + m.id + '">' + TT.esc(TT.t("nav.delete")) + '</button>' : '<span class="muted">' + TT.esc(TT.t("menu.plugin_managed")) + '</span>') + '</td></tr>';
    }).join("");
    document.querySelectorAll("[data-edit-menu]").forEach(function (b) { b.addEventListener("click", function () { openMenu(menus.find(function (m) { return m.id === parseInt(b.getAttribute("data-edit-menu"), 10); })); }); });
    document.querySelectorAll("[data-delete-menu]").forEach(function (b) { b.addEventListener("click", async function () {
      if (!window.confirm(TT.t("menu.delete_confirm"))) return;
      var res = await TT.api("/api/admin/menus/" + b.getAttribute("data-delete-menu"), "DELETE");
      TT.toast(res.message, res.success ? "success" : "error"); if (res.success) loadMenus();
    }); });
  }
  function openMenu(m) {
    var f = document.getElementById("menu-form"); f.reset();
    f.elements.id.value = m ? m.id : ""; f.elements.enabled.checked = m ? m.enabled : true;
    if (m) { f.elements.label.value = m.label; f.elements.url.value = m.url; f.elements.icon.value = m.icon; f.elements.role.value = m.role; f.elements.order.value = m.order; }
    f.querySelector(".form-error").hidden = true;
    document.getElementById("menu-dialog").showModal();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var loaders = { general: loadGeneral, fields: loadFields, dashboard: loadDefaults, themes: loadThemes, menus: loadMenus };
    document.querySelectorAll("[data-settings-tab]").forEach(function (tab) { tab.addEventListener("click", function () {
      var key = tab.getAttribute("data-settings-tab");
      document.querySelectorAll("[data-settings-tab]").forEach(function (t) { t.classList.toggle("active", t === tab); });
      document.querySelectorAll(".settings-panel").forEach(function (p) { p.hidden = p.id !== "settings-" + key; });
      loaders[key]();
    }); });
    loadGeneral();
    document.getElementById("general-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var f = ev.target; f.querySelector(".form-error").hidden = true;
      var values = { "site.name": f.elements["site.name"].value, "site.contact_phone": f.elements["site.contact_phone"].value, "site.contact_message": f.elements["site.contact_message"].value, "site.registration_enabled": f.elements["site.registration_enabled"].checked, "site.maintenance": f.elements["site.maintenance"].checked };
      var out = await TT.api("/api/admin/settings", "POST", { values: values });
      TT.toast(out.message, out.success ? "success" : "error"); if (!out.success) showErr(f, out.message);
    });
    document.getElementById("logo-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var f = ev.target; f.querySelector(".form-error").hidden = true;
      if (!f.elements.file.files.length) return showErr(f, TT.t("err.file_required"));
      var out = await TT.upload("/api/admin/logo", new FormData(f));
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) document.getElementById("logo-preview").src = "/branding/logo?" + Date.now(); else showErr(f, out.message);
    });
    document.getElementById("add-field").addEventListener("click", function () { openField(null); });
    document.getElementById("field-type").addEventListener("change", function (ev) { document.getElementById("field-options-wrap").hidden = ev.target.value !== "select"; });
    document.getElementById("field-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var f = ev.target; f.querySelector(".form-error").hidden = true;
      var id = f.elements.id.value;
      var body = { label: f.elements.label.value, options: f.elements.options.value.split("\n").map(function (s) { return s.trim(); }).filter(Boolean), required: f.elements.required.checked, enabled: f.elements.enabled.checked, sort_order: parseInt(f.elements.sort_order.value, 10) || 0 };
      if (!id) { body.applies_to = f.elements.applies_to.value; body.machine_name = f.elements.machine_name.value; body.field_type = f.elements.field_type.value; }
      var out = await TT.api(id ? "/api/custom-fields/" + id : "/api/custom-fields", "POST", body);
      if (out.success) { document.getElementById("field-dialog").close(); TT.toast(out.message, "success"); loadFields(); } else showErr(f, out.message);
    });
    document.getElementById("dashboard-role").addEventListener("change", loadDefaults);
    document.getElementById("save-default-blocks").addEventListener("click", async function () {
      var out = await TT.api("/api/admin/dashboard/defaults", "POST", { role: document.getElementById("dashboard-role").value, blocks: defaultBlocks });
      TT.toast(out.message, out.success ? "success" : "error");
    });
    document.getElementById("theme-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var f = ev.target; f.querySelector(".form-error").hidden = true;
      var body = formData(f); body.radius = parseInt(body.radius, 10);
      var out = await TT.api("/api/admin/themes", "POST", body);
      TT.toast(out.message, out.success ? "success" : "error"); if (out.success) { f.reset(); loadThemes(); } else showErr(f, out.message);
    });
    document.getElementById("role-theme-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var body = formData(ev.target);
      var out = await TT.api("/api/admin/themes/role", "POST", body);
      TT.toast(out.message, out.success ? "success" : "error");
    });
    document.getElementById("add-menu").addEventListener("click", function () { openMenu(null); });
    document.getElementById("menu-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var f = ev.target; f.querySelector(".form-error").hidden = true;
      var body = formData(f); body.order = parseInt(body.order, 10) || 0; body.enabled = f.elements.enabled.checked;
      var id = body.id; delete body.id;
      var out = await TT.api(id ? "/api/admin/menus/" + id : "/api/admin/menus", "POST", body);
      if (out.success) { document.getElementById("menu-dialog").close(); TT.toast(out.message, "success"); loadMenus(); } else showErr(f, out.message);
    });
  });
})();
