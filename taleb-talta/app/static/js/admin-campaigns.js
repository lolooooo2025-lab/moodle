(function () {
  "use strict";
  function nextFriday() { var d = new Date(); d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7)); return d.toISOString().slice(0, 10); }
  async function load() {
    var out = await TT.api("/api/admin/campaigns", "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    var body = document.getElementById("campaigns-body");
    body.innerHTML = out.data.map(function (c) {
      var actions = c.status === "scheduled" ? '<button class="btn btn-ghost btn-sm" data-edit="' + c.id + '">' + TT.t("campaign.edit") + '</button> <button class="btn btn-primary btn-sm" data-publish="' + c.id + '">' + TT.t("campaign.publish") + '</button> <button class="btn btn-danger btn-sm" data-cancel="' + c.id + '">' + TT.t("campaign.cancel") + '</button>' : (c.status === "published" ? '<a class="btn btn-ghost btn-sm" href="/campaigns/' + c.id + '">' + TT.t("nav.open") + '</a>' : '');
      return '<tr><td dir="ltr">' + c.week_date + '</td><td>' + TT.esc(c.title) + '</td><td><span class="badge badge-' + (c.status === "published" ? "approved" : c.status === "scheduled" ? "pending" : "rejected") + '">' + TT.t("campaign." + c.status) + '</span></td><td>' + new Date(c.publish_at).toLocaleString("ar-EG") + '</td><td class="row">' + actions + '</td></tr>';
    }).join("");
    body.querySelectorAll("[data-edit]").forEach(function (b) { b.addEventListener("click", function () {
      var c = out.data.find(function (x) { return x.id === Number(b.dataset.edit); });
      document.getElementById("campaign-id").value = c.id; document.getElementById("campaign-week").value = c.week_date;
      document.getElementById("campaign-title").value = c.title; document.getElementById("campaign-body").value = c.body;
      document.getElementById("campaign-form-title").textContent = TT.t("campaign.edit");
    }); });
    body.querySelectorAll("[data-publish]").forEach(function (b) { b.addEventListener("click", async function () { var r = await TT.api("/api/admin/campaigns/" + b.dataset.publish + "/publish", "POST", {}); TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load(); }); });
    body.querySelectorAll("[data-cancel]").forEach(function (b) { b.addEventListener("click", async function () { var r = await TT.api("/api/admin/campaigns/" + b.dataset.cancel + "/cancel", "POST", {}); TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load(); }); });
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("campaign-week").value = nextFriday();
    document.getElementById("campaign-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var id = document.getElementById("campaign-id").value;
      var out = await TT.api("/api/admin/campaigns" + (id ? "/" + id : ""), "POST", { week_date: document.getElementById("campaign-week").value, title: document.getElementById("campaign-title").value, body: document.getElementById("campaign-body").value });
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) { this.reset(); document.getElementById("campaign-id").value = ""; document.getElementById("campaign-week").value = nextFriday(); document.getElementById("campaign-form-title").textContent = TT.t("notif.friday"); load(); }
    });
    load();
  });
})();
