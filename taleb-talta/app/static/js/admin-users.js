/* Admin users: search/filter/paginate, guarded edits, divisions. */
(function () {
  "use strict";
  var page = 1, pages = 1, rows = [], divisions = [], userFields = [];
  function qs() {
    var f = document.getElementById("user-filters");
    var p = new URLSearchParams(new FormData(f));
    p.set("page", page);
    return p.toString();
  }
  async function load() {
    var out = await TT.api("/api/admin/users?" + qs(), "GET");
    if (!out.success) return TT.toast(out.message, "error");
    rows = out.data.rows; pages = out.data.pages; page = out.data.page;
    document.getElementById("users-total").textContent = TT.t("admin.users_count", { count: out.data.total });
    document.getElementById("users-page").textContent = TT.t("misc.page_of", { page: page, pages: pages });
    document.getElementById("users-prev").disabled = page <= 1;
    document.getElementById("users-next").disabled = page >= pages;
    document.getElementById("users-body").innerHTML = rows.map(function (u) {
      var div = divisions.find(function (d) { return String(d.id) === String(u.division_id); });
      return '<tr data-user="' + u.id + '"><td>' + TT.esc(u.name) + '</td><td dir="ltr">' + TT.esc(u.phone) + '</td><td>' + TT.esc(TT.t("role." + u.role)) + '</td><td><span class="badge">' + TT.esc(TT.t("status." + u.status)) + '</span></td><td>' + TT.esc(div ? div.name : "—") + '</td><td class="actions"><button class="btn btn-ghost btn-sm" data-edit-user="' + u.id + '">' + TT.esc(TT.t("nav.edit")) + '</button>' + (u.status === "banned" ? '<button class="btn btn-ghost btn-sm" data-unban="' + u.id + '">' + TT.esc(TT.t("admin.unban")) + '</button>' : '') + '</td></tr>';
    }).join("");
    document.querySelectorAll("[data-edit-user]").forEach(function (b) { b.addEventListener("click", function () { edit(parseInt(b.getAttribute("data-edit-user"), 10)); }); });
    document.querySelectorAll("[data-unban]").forEach(function (b) { b.addEventListener("click", async function () {
      var out = await TT.api("/api/users/unban", "POST", { user_id: parseInt(b.getAttribute("data-unban"), 10) });
      TT.toast(out.message, out.success ? "success" : "error"); if (out.success) load();
    }); });
  }
  async function edit(id) {
    var u = rows.find(function (r) { return r.id === id; });
    var f = document.getElementById("user-edit-form");
    f.elements.id.value = u.id; f.elements.name.value = u.name; f.elements.phone.value = u.phone;
    f.elements.guardian_phone.value = u.guardian_phone; f.elements.role.value = u.role;
    f.elements.status.value = u.status; f.elements.division_id.value = u.division_id || "";
    var out = await TT.api("/api/custom-fields/user/" + id + "/values", "GET");
    TTCustomFields.render(document.getElementById("user-custom-fields"), userFields, out.success ? out.data : {}, "user-cf");
    f.querySelector(".form-error").hidden = true;
    document.getElementById("user-dialog").showModal();
  }
  document.addEventListener("DOMContentLoaded", async function () {
    divisions = Array.from(document.querySelectorAll("#user-division option[value]")).map(function (o) { return { id: o.value, name: o.textContent }; }).filter(function (d) { return d.id !== "0"; });
    var cf = await TT.api("/api/custom-fields/user", "GET");
    userFields = cf.success ? cf.data : [];
    document.querySelectorAll("[data-user-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll("[data-user-tab]").forEach(function (t) { t.classList.toggle("active", t === tab); });
        document.getElementById("users-panel").hidden = tab.getAttribute("data-user-tab") !== "users";
        document.getElementById("divisions-panel").hidden = tab.getAttribute("data-user-tab") !== "divisions";
      });
    });
    document.getElementById("user-filters").addEventListener("submit", function (ev) { ev.preventDefault(); page = 1; load(); });
    document.getElementById("users-prev").addEventListener("click", function () { page--; load(); });
    document.getElementById("users-next").addEventListener("click", function () { page++; load(); });
    document.getElementById("user-edit-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var f = ev.target, data = new FormData(f), err = f.querySelector(".form-error");
      var body = { name: data.get("name"), phone: data.get("phone"), guardian_phone: data.get("guardian_phone"), role: data.get("role"), status: data.get("status"), division_id: data.get("division_id") ? parseInt(data.get("division_id"), 10) : null, custom_fields: TTCustomFields.collect(document.getElementById("user-custom-fields")) };
      var out = await TT.api("/api/admin/users/" + data.get("id"), "POST", body);
      if (out.success) { document.getElementById("user-dialog").close(); TT.toast(out.message, "success"); load(); }
      else { err.textContent = out.message; err.hidden = false; }
    });
    document.getElementById("division-create").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var f = ev.target, out = await TT.api("/api/admin/divisions", "POST", { name: f.elements.name.value });
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) setTimeout(function () { location.reload(); }, 500);
    });
    document.querySelectorAll("[data-rename-division]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var name = window.prompt(TT.t("admin.division_rename"), b.getAttribute("data-name"));
        if (name === null) return;
        var out = await TT.api("/api/admin/divisions/" + b.getAttribute("data-rename-division"), "POST", { name: name });
        TT.toast(out.message, out.success ? "success" : "error");
        if (out.success) setTimeout(function () { location.reload(); }, 500);
      });
    });
    load();
  });
})();
