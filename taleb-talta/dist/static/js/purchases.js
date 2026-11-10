(function () {
  "use strict";
  function money(c) { return new Intl.NumberFormat("ar-EG", { style: "currency", currency: "EGP" }).format(c / 100); }
  async function load() {
    var out = await TT.api("/api/purchases", "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    var body = document.getElementById("purchases-body");
    document.getElementById("purchases-empty").hidden = out.data.length > 0;
    body.innerHTML = out.data.map(function (p) {
      var action = p.status === "pending" ? '<button class="btn btn-ghost btn-sm" data-cancel="' + p.id + '">' + TT.t("buy.cancel") + '</button>' : (p.status === "confirmed" ? '<a class="btn btn-primary btn-sm" href="/courses/' + p.course_id + '">' + TT.t("buy.unlock") + '</a>' : '');
      return '<tr><td>' + p.id + '</td><td>' + TT.esc(p.course_title) + '</td><td>' + TT.esc(p.lesson_title || "—") + '</td><td>' + money(p.amount_cents) + '</td><td><span class="badge badge-' + (p.status === "confirmed" ? "approved" : p.status === "pending" ? "pending" : "rejected") + '">' + TT.t("buy." + p.status) + '</span></td><td>' + TT.esc(p.review_note || "—") + '</td><td>' + action + '</td></tr>';
    }).join("");
    body.querySelectorAll("[data-cancel]").forEach(function (b) { b.addEventListener("click", async function () {
      var r = await TT.api("/api/purchases/" + b.dataset.cancel + "/cancel", "POST", {});
      TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load();
    }); });
  }
  document.addEventListener("DOMContentLoaded", load);
})();
