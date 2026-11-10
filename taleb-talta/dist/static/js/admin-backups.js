/* Owner-only real backup artifacts. */
(function () {
  "use strict";
  function size(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.round(n / 1024) + " KB"; }
  async function load() {
    var out = await TT.api("/api/admin/backups", "GET");
    if (!out.success) return TT.toast(out.message, "error");
    document.getElementById("backups-body").innerHTML = out.data.length ? out.data.map(function (b) {
      return '<tr><td dir="ltr">' + TT.esc(b.file_name) + '</td><td>' + TT.esc(TT.t("backup.status_" + b.status)) + '</td><td dir="ltr">' + size(b.size) + '</td><td dir="ltr">' + TT.esc(b.created_at.replace("T", " ").slice(0, 16)) + '</td><td class="actions">' + (b.status === "ready" ? '<a class="btn btn-ghost btn-sm" download href="/api/admin/backups/' + b.id + '/download">' + TT.esc(TT.t("misc.download")) + '</a>' : '') + '<button class="btn btn-danger btn-sm" data-delete-backup="' + b.id + '">' + TT.esc(TT.t("nav.delete")) + '</button></td></tr>';
    }).join("") : '<tr><td colspan="5" class="muted">' + TT.esc(TT.t("backup.none")) + '</td></tr>';
    document.querySelectorAll("[data-delete-backup]").forEach(function (b) { b.addEventListener("click", async function () {
      if (!window.confirm(TT.t("backup.delete_confirm"))) return;
      var res = await TT.api("/api/admin/backups/" + b.getAttribute("data-delete-backup"), "DELETE");
      TT.toast(res.message, res.success ? "success" : "error"); if (res.success) load();
    }); });
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("backup-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var btn = ev.target.querySelector("button"); btn.disabled = true;
      var out = await TT.api("/api/admin/backups", "POST", { include_uploads: ev.target.elements.include_uploads.checked });
      TT.toast(out.message, out.success ? "success" : "error"); btn.disabled = false; load();
    });
    load();
    setInterval(function () {
      var creating = document.querySelector('#backups-body td');
      if (document.querySelector('#backups-body') && document.querySelector('#backups-body').textContent.indexOf(TT.t('backup.status_creating')) !== -1) load();
    }, 5000);
  });
})();
