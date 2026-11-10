(function () {
  "use strict";
  function fill(sel, rows, value, label) { sel.innerHTML = rows.map(function (r) { return '<option value="' + TT.esc(r[value]) + '">' + TT.esc(r[label]) + '</option>'; }).join(""); }
  function targets() {
    var a = document.getElementById("bc-audience").value;
    document.querySelectorAll("[data-target]").forEach(function (el) { el.hidden = el.dataset.target !== a; });
  }
  async function history() {
    var out = await TT.api("/api/admin/notifications", "GET");
    if (!out.success) return;
    document.getElementById("broadcast-history").innerHTML = out.data.map(function (n) {
      var audience = n.campaign_id ? TT.t("notif.friday") : TT.t("notif.new");
      return '<tr><td>' + TT.esc(n.title) + '<div class="muted small">' + TT.esc(n.body.slice(0, 100)) + '</div></td><td>' + audience + '</td><td>' + n.recipients + '</td><td>' + new Date(n.created_at).toLocaleString("ar-EG") + '</td></tr>';
    }).join("");
  }
  document.addEventListener("DOMContentLoaded", async function () {
    var meta = await TT.api("/api/admin/notifications/meta", "GET");
    if (!meta.success) { TT.toast(meta.message, "error"); return; }
    fill(document.getElementById("bc-role"), meta.data.roles.map(function (r) { return { id: r, name: TT.t("role." + r) }; }), "id", "name");
    fill(document.getElementById("bc-division"), meta.data.divisions, "id", "name");
    fill(document.getElementById("bc-course"), meta.data.courses, "id", "title");
    document.getElementById("bc-audience").addEventListener("change", targets); targets();
    var timer;
    document.getElementById("bc-user-search").addEventListener("input", function () {
      clearTimeout(timer); var q = this.value;
      timer = setTimeout(async function () {
        var out = await TT.api("/api/admin/notifications/users?q=" + encodeURIComponent(q), "GET");
        if (out.success) fill(document.getElementById("bc-user"), out.data.map(function (u) { return { id: u.id, name: u.name + " · " + u.phone }; }), "id", "name");
      }, 250);
    });
    document.getElementById("broadcast-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var a = document.getElementById("bc-audience").value;
      var data = { title: document.getElementById("bc-title").value, body: document.getElementById("bc-body").value, url: document.getElementById("bc-url").value, audience: a,
        role: a === "role" ? document.getElementById("bc-role").value : "", division_id: a === "division" ? Number(document.getElementById("bc-division").value) : 0,
        course_id: a === "course" ? Number(document.getElementById("bc-course").value) : 0, user_id: a === "user" ? Number(document.getElementById("bc-user").value) : 0 };
      var out = await TT.api("/api/admin/notifications", "POST", data);
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) { this.reset(); targets(); history(); }
    });
    history();
  });
})();
