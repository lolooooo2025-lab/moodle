/* Staff moderation: reports, sticker approval, editable dictionary, restrictions. */
(function () {
  "use strict";
  var L = TT.labels, overview = null, pendingDecision = null;
  function el(id) { return document.getElementById(id); }
  function notify(out) { TT.toast(out.message || L.generic, out.success ? "success" : "error"); return out.success; }
  function entityLabel(type) { return L["entity_" + type] || type; }
  function reportCard(r) {
    var actions = "";
    if (r.status === "pending") {
      actions = '<div class="row mt-1"><button class="btn btn-ghost btn-sm" data-decision="approve" data-id="' + r.id + '">' + TT.esc(L.approve) + '</button>' +
        '<button class="btn btn-ghost btn-sm" data-decision="remove" data-id="' + r.id + '">' + TT.esc(L.remove) + '</button>' +
        '<button class="btn btn-ghost btn-sm" data-decision="warn" data-id="' + r.id + '">' + TT.esc(L.warn) + '</button>' +
        (TT.page.canBan ? '<button class="btn btn-danger btn-sm" data-decision="ban" data-id="' + r.id + '">' + TT.esc(L.ban) + '</button>' : '') + '</div>';
    }
    return '<article class="card report-card"><div class="spread mb-1"><span class="chip">' + TT.esc(entityLabel(r.entity_type)) + '</span><time class="muted small">' + TT.community.fmtDate(r.created_at) + '</time></div>' +
      '<h3 class="m-0">' + TT.esc(r.target_name) + '</h3><p class="small muted">' + TT.esc(L.by) + ' ' + TT.esc(r.reporter) + '</p>' +
      '<p class="pre-wrap">' + TT.esc(r.reason) + '</p><details class="mb-1"><summary>' + TT.esc(L.snapshot) + '</summary><p class="pre-wrap snapshot">' + TT.esc(r.snapshot) + '</p></details>' +
      '<a class="btn btn-ghost btn-sm" href="' + TT.esc(r.link) + '">' + TT.esc(L.view) + '</a>' + actions + '</article>';
  }
  function stickerCard(s) {
    return '<article class="card"><img class="sticker-preview" src="' + TT.esc(s.url) + '" alt="' + TT.esc(s.title) + '"><h3>' + TT.esc(s.title) + '</h3><p class="muted small">' + TT.esc(L.by) + ' ' + TT.esc(s.owner) + '</p>' +
      '<div class="row"><button class="btn btn-primary btn-sm" data-sticker-approve="' + s.id + '">' + TT.esc(L.stickerApprove) + '</button><button class="btn btn-ghost btn-sm" data-sticker-reject="' + s.id + '">' + TT.esc(L.stickerReject) + '</button></div></article>';
  }
  function bindReports() {
    el("report-list").querySelectorAll("[data-decision]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var action = btn.dataset.decision, id = Number(btn.dataset.id);
        if (action === "approve") decideReport(id, action, "");
        else openDecision({ kind: "report", id: id, action: action }, L[action]);
      });
    });
  }
  async function loadReports() {
    var out = await TT.api("/api/moderation/reports?status=" + encodeURIComponent(el("report-status").value), "GET");
    if (!out.success) { notify(out); return; }
    el("report-list").innerHTML = out.data.map(reportCard).join("");
    el("reports-empty").hidden = out.data.length > 0;
    bindReports();
  }
  async function loadStickers() {
    var out = await TT.api("/api/stickers/pending", "GET");
    if (!out.success) return;
    el("pending-stickers").innerHTML = out.data.map(stickerCard).join("");
    el("mod-stickers-empty").hidden = out.data.length > 0;
    el("pending-stickers").querySelectorAll("[data-sticker-approve]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var res = await TT.api("/api/stickers/" + btn.dataset.stickerApprove + "/approve", "POST", { reason: "" });
        if (notify(res)) loadAll();
      });
    });
    el("pending-stickers").querySelectorAll("[data-sticker-reject]").forEach(function (btn) {
      btn.addEventListener("click", function () { openDecision({ kind: "sticker", id: Number(btn.dataset.stickerReject) }, L.stickerReject); });
    });
  }
  async function loadWords() {
    var out = await TT.api("/api/moderation/profanity", "GET");
    if (!out.success) return;
    el("word-list").innerHTML = out.data.map(function (w) {
      return '<div class="spread word-row"><span class="dictionary-word">' + TT.esc(w.word) + '</span><button class="btn btn-ghost btn-sm" data-word="' + w.id + '" data-enabled="' + (w.enabled ? "0" : "1") + '">' + TT.esc(w.enabled ? L.disable : L.enable) + '</button></div>';
    }).join("");
    el("word-list").querySelectorAll("[data-word]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var res = await TT.api("/api/moderation/profanity/" + btn.dataset.word + "/state", "POST", { enabled: btn.dataset.enabled === "1" });
        if (notify(res)) loadWords();
      });
    });
  }
  async function loadOverview() {
    var out = await TT.api("/api/moderation/overview", "GET");
    if (!out.success) return;
    overview = out.data;
    el("report-count").textContent = overview.reports;
    el("sticker-count").textContent = overview.stickers;
    el("restriction-count").textContent = overview.restrictions.length;
    el("restriction-list").innerHTML = overview.restrictions.map(function (r) {
      return '<article class="card"><div class="spread"><h3 class="m-0">' + TT.esc(r.name) + '</h3>' +
        (overview.can_ban ? '<button class="btn btn-ghost btn-sm" data-lift="' + r.id + '">' + TT.esc(L.lift) + '</button>' : '') + '</div>' +
        '<p class="muted small">' + TT.esc(L.until) + ' ' + TT.community.fmtDate(r.expires_at) + '</p><p class="pre-wrap">' + TT.esc(r.reason) + '</p></article>';
    }).join("");
    el("restrictions-empty").hidden = overview.restrictions.length > 0;
    el("restriction-list").querySelectorAll("[data-lift]").forEach(function (btn) {
      btn.addEventListener("click", function () { openDecision({ kind: "lift", id: Number(btn.dataset.lift) }, L.liftReason); });
    });
    el("alert-list").innerHTML = overview.alerts.map(function (a) {
      return '<article class="card alert-item"><strong>' + TT.esc(L.loginAlert) + '</strong><p class="m-0">' + TT.esc(a.name || String(a.user_id || "")) + '</p><time class="muted small">' + TT.community.fmtDate(a.created_at) + '</time></article>';
    }).join("");
    el("alerts-empty").hidden = overview.alerts.length > 0;
  }
  function openDecision(state, title) {
    pendingDecision = state;
    el("decision-title").textContent = title;
    el("decision-reason").value = "";
    el("decision-dialog").showModal();
    el("decision-reason").focus();
  }
  async function decideReport(id, action, reason) {
    var out = await TT.api("/api/moderation/reports/" + id + "/decide", "POST", { action: action, reason: reason });
    if (notify(out)) loadAll();
  }
  async function loadAll() {
    await Promise.all([loadReports(), loadStickers(), loadWords(), loadOverview()]);
  }
  document.addEventListener("DOMContentLoaded", function () {
    // The shared date helper is optional on this page; use the same local formatter.
    TT.communityDate = function (value) {
      try { return new Intl.DateTimeFormat("ar-EG", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
      catch (e) { return value || ""; }
    };
    TT.community.bindDialogs();
    document.querySelectorAll("[data-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("active", b === btn); b.setAttribute("aria-selected", b === btn ? "true" : "false"); });
        document.querySelectorAll("[data-pane]").forEach(function (p) { p.hidden = p.dataset.pane !== btn.dataset.tab; });
      });
    });
    el("report-status").addEventListener("change", loadReports);
    el("refresh-moderation").addEventListener("click", loadAll);
    el("word-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var out = await TT.api("/api/moderation/profanity", "POST", { word: el("new-word").value.trim(), enabled: true });
      if (notify(out)) { el("new-word").value = ""; loadWords(); }
    });
    el("decision-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      if (!pendingDecision) return;
      var reason = el("decision-reason").value.trim(); if (!reason) return;
      var btn = this.querySelector('[type="submit"]'); btn.disabled = true;
      var d = pendingDecision, out;
      if (d.kind === "report") out = await TT.api("/api/moderation/reports/" + d.id + "/decide", "POST", { action: d.action, reason: reason });
      else if (d.kind === "sticker") out = await TT.api("/api/stickers/" + d.id + "/reject", "POST", { reason: reason });
      else out = await TT.api("/api/moderation/restrictions/lift", "POST", { restriction_id: d.id, reason: reason });
      btn.disabled = false;
      if (notify(out)) { el("decision-dialog").close(); pendingDecision = null; loadAll(); }
    });
    loadAll();
  });
})();
