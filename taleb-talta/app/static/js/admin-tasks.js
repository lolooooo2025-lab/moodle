/* Cron schedule editor + manual runs + history. */
(function () {
  "use strict";
  var tasks = [];
  function when(iso) { return iso ? iso.replace("T", " ").slice(0, 16) : "—"; }
  async function load() {
    var out = await TT.api("/api/admin/tasks", "GET");
    if (!out.success) return TT.toast(out.message, "error");
    tasks = out.data.tasks;
    document.getElementById("tasks-body").innerHTML = tasks.map(function (t) {
      var s = t.schedule;
      return '<tr><td><code dir="ltr">' + TT.esc(t.key) + '</code>' + (t.plugin ? '<br><span class="muted">' + TT.esc(t.plugin) + '</span>' : '') + '</td><td dir="ltr">' + TT.esc([s.minute, s.hour, s.day, s.month, s.dayofweek].join(" ")) + '</td><td dir="ltr">' + when(t.next_run) + '</td><td dir="ltr">' + when(t.last_run) + '</td><td>' + TT.esc(TT.t(t.enabled ? "misc.enabled" : "misc.disabled")) + (t.locked ? ' · ' + TT.esc(TT.t("cron.running")) : '') + '</td><td class="actions"><button class="btn btn-ghost btn-sm" data-edit-task="' + t.id + '">' + TT.esc(TT.t("nav.edit")) + '</button><button class="btn btn-primary btn-sm" data-run-task="' + t.id + '" ' + (t.enabled ? '' : 'disabled') + '>' + TT.esc(TT.t("cron.run_now")) + '</button></td></tr>';
    }).join("");
    document.getElementById("runs-body").innerHTML = out.data.runs.map(function (r) {
      return '<tr><td><code dir="ltr">' + TT.esc(r.task) + '</code></td><td><span class="badge badge-task-' + TT.esc(r.status) + '">' + TT.esc(TT.t("cron.status_" + r.status)) + '</span></td><td dir="ltr">' + when(r.started_at) + '</td><td><code dir="ltr">' + TT.esc(r.error || JSON.stringify(r.detail)) + '</code></td></tr>';
    }).join("");
    document.querySelectorAll("[data-edit-task]").forEach(function (b) { b.addEventListener("click", function () {
      var t = tasks.find(function (x) { return x.id === parseInt(b.getAttribute("data-edit-task"), 10); });
      var f = document.getElementById("task-form"); f.elements.id.value = t.id;
      ["minute", "hour", "day", "month", "dayofweek"].forEach(function (k) { f.elements[k].value = t.schedule[k]; });
      f.elements.enabled.checked = t.enabled; f.querySelector(".form-error").hidden = true;
      document.getElementById("task-dialog").showModal();
    }); });
    document.querySelectorAll("[data-run-task]").forEach(function (b) { b.addEventListener("click", async function () {
      b.disabled = true;
      var res = await TT.api("/api/admin/tasks/" + b.getAttribute("data-run-task") + "/run", "POST", {});
      TT.toast(res.message, res.success ? "success" : "error"); load();
    }); });
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("task-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var f = ev.target, body = {};
      ["minute", "hour", "day", "month", "dayofweek"].forEach(function (k) { body[k] = f.elements[k].value; });
      body.enabled = f.elements.enabled.checked;
      var out = await TT.api("/api/admin/tasks/" + f.elements.id.value, "POST", body);
      if (out.success) { document.getElementById("task-dialog").close(); TT.toast(out.message, "success"); load(); }
      else { var e = f.querySelector(".form-error"); e.textContent = out.message; e.hidden = false; }
    });
    load();
  });
})();
