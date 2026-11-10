/* Library moderation queue — approve / reject (with reason). */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};

  function card(it) {
    return '<div class="card" data-item="' + it.id + '">' +
      '<div class="spread"><div>' +
      '<div class="row"><span class="chip">' + TT.esc(it.category || "—") + "</span>" +
      '<span class="badge badge-pending">' + L.pending + "</span></div>" +
      "<h3 class='lib-q-title'>" + TT.esc(it.title) + "</h3>" +
      '<div class="muted small">' + L.by + " " + TT.esc(it.uploader_name || "") + "</div>" +
      (it.description ? '<p class="muted">' + TT.esc(it.description) + "</p>" : "") +
      "</div>" +
      '<a class="btn btn-ghost btn-sm" href="/api/library/' + it.id + '/download">' + L.download + "</a></div>" +
      '<div class="row mt-1">' +
      '<button class="btn btn-success btn-sm" data-approve="' + it.id + '">' + L.approve + "</button>" +
      '<input type="text" class="reason-input input-inline flex-1 min-w-180" placeholder="' + L.reasonPh + '">' +
      '<button class="btn btn-danger btn-sm" data-reject="' + it.id + '">' + L.reject + "</button>" +
      "</div></div>";
  }

  async function load() {
    var out = await TT.api("/api/library/pending", "GET");
    var wrap = document.getElementById("pending-list");
    var empty = document.getElementById("pending-empty");
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    wrap.innerHTML = out.data.map(card).join("");
    empty.hidden = out.data.length > 0;
    wrap.querySelectorAll("[data-approve]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var r = await TT.api("/api/library/" + b.getAttribute("data-approve") + "/approve", "POST", {});
        TT.toast(r.message, r.success ? "success" : "error");
        if (r.success) load();
      });
    });
    wrap.querySelectorAll("[data-reject]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var cardEl = b.closest("[data-item]");
        var reason = cardEl.querySelector(".reason-input").value;
        var r = await TT.api("/api/library/" + b.getAttribute("data-reject") + "/reject", "POST", { reason: reason });
        TT.toast(r.message, r.success ? "success" : "error");
        if (r.success) load();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", load);
})();
