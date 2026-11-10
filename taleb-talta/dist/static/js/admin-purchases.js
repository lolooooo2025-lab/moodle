(function () {
  "use strict";
  var current = null, offset = 0;
  function money(c) { return new Intl.NumberFormat("ar-EG", { style: "currency", currency: "EGP" }).format(c / 100); }
  async function load() {
    var status = document.getElementById("purchase-filter").value;
    var out = await TT.api("/api/admin/purchases?offset=" + offset + "&status=" + encodeURIComponent(status), "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    document.getElementById("pending-count").textContent = TT.t("buy.pending_count") + ": " + (out.data.counts.pending || 0);
    var body = document.getElementById("purchases-body");
    document.getElementById("purchase-prev").disabled = offset === 0;
    document.getElementById("purchase-next").disabled = !out.data.has_more;
    body.innerHTML = out.data.rows.map(function (p) {
      var action = p.status === "pending" ? '<button class="btn btn-primary btn-sm" data-review="' + p.id + '">' + TT.t("buy.review") + '</button>' : TT.esc(p.review_note || "");
      return '<tr><td>' + p.id + '</td><td>' + TT.esc(p.user_name) + '<div class="muted small" dir="ltr">' + TT.esc(p.phone) + '</div></td><td>' + TT.esc(p.course_title) + '</td><td>' + TT.esc(p.lesson_title || "—") + '</td><td>' + money(p.amount_cents) + '</td><td>' + TT.esc(p.reference) + '<div class="muted small">' + TT.esc(p.note) + '</div></td><td><span class="badge badge-' + (p.status === "confirmed" ? "approved" : p.status === "pending" ? "pending" : "rejected") + '">' + TT.t("buy." + p.status) + '</span></td><td>' + action + '</td></tr>';
    }).join("");
    body.querySelectorAll("[data-review]").forEach(function (b) { b.addEventListener("click", function () {
      current = out.data.rows.find(function (p) { return p.id === Number(b.dataset.review); });
      document.getElementById("review-summary").textContent = current.user_name + " · " + current.course_title + " · " + money(current.amount_cents) + " · " + current.reference;
      document.getElementById("review-note").value = "";
      document.getElementById("review-dialog").showModal();
    }); });
  }
  async function review(action) {
    if (!current) return;
    var out = await TT.api("/api/admin/purchases/" + current.id + "/" + action, "POST", { note: document.getElementById("review-note").value });
    TT.toast(out.message, out.success ? "success" : "error");
    if (out.success) { document.getElementById("review-dialog").close(); load(); }
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("purchase-filter").addEventListener("change", function () { offset = 0; load(); });
    document.getElementById("purchase-prev").addEventListener("click", function () { offset = Math.max(0, offset - 100); load(); });
    document.getElementById("purchase-next").addEventListener("click", function () { offset += 100; load(); });
    document.getElementById("confirm-purchase").addEventListener("click", function () { review("confirm"); });
    document.getElementById("reject-purchase").addEventListener("click", function () { review("reject"); });
    load();
  });
})();
