/* Shared community helpers: safe dates, native dialogs and content reporting. */
(function () {
  "use strict";
  var L = TT.labels || {};
  function fmtDate(value) {
    if (!value) return "";
    try { return new Intl.DateTimeFormat("ar-EG", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
    catch (e) { return value; }
  }
  function bindDialogs(root) {
    (root || document).querySelectorAll("[data-close-dialog]").forEach(function (btn) {
      btn.addEventListener("click", function () { btn.closest("dialog").close(); });
    });
  }
  var dialog, form, reason, targetType, targetId;
  function ensureReportDialog() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.className = "community-dialog";
    dialog.id = "community-report-dialog";
    dialog.innerHTML = '<form class="stack" id="community-report-form"><h2>' + TT.esc(L.report) + '</h2>' +
      '<div class="field"><label for="community-report-reason">' + TT.esc(L.reportReason) + '</label>' +
      '<textarea id="community-report-reason" rows="4" maxlength="2000" required placeholder="' + TT.esc(L.reportPh) + '"></textarea></div>' +
      '<div class="row"><button type="submit" class="btn btn-primary">' + TT.esc(L.report) + '</button>' +
      '<button type="button" class="btn btn-ghost" data-close-dialog>' + TT.esc(L.cancel) + '</button></div></form>';
    document.body.appendChild(dialog);
    bindDialogs(dialog);
    form = dialog.querySelector("form");
    reason = dialog.querySelector("textarea");
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var btn = form.querySelector('[type="submit"]');
      btn.disabled = true;
      try {
        var out = await TT.api("/api/moderation/reports", "POST", { entity_type: targetType, entity_id: targetId, reason: reason.value.trim() });
        TT.toast(out.message || L.generic, out.success ? "success" : "error");
        if (out.success) { dialog.close(); form.reset(); }
      } catch (e) { TT.toast(L.generic, "error"); }
      finally { btn.disabled = false; }
    });
  }
  function report(type, id) {
    ensureReportDialog();
    targetType = type; targetId = Number(id);
    dialog.showModal();
    reason.focus();
  }
  TT.community = { fmtDate: fmtDate, bindDialogs: bindDialogs, report: report };
})();
