(function () {
  "use strict";
  var rows = [], keyStream = null;
  function fill(sel, data, value, label) { sel.innerHTML = data.map(function (r) { return '<option value="' + TT.esc(r[value]) + '">' + TT.esc(r[label]) + '</option>'; }).join(""); }
  function targets() { var a = document.getElementById("st-audience").value; document.querySelectorAll("[data-st-target]").forEach(function (el) { el.hidden = el.dataset.stTarget !== a; }); }
  function localInput(iso) { var d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); }
  function openForm(row) {
    document.getElementById("stream-id").value = row ? row.id : "";
    document.getElementById("stream-dialog-title").textContent = TT.t(row ? "stream.edit" : "stream.new");
    document.getElementById("st-title").value = row ? row.title : "";
    document.getElementById("st-description").value = row ? row.description : "";
    document.getElementById("st-audience").value = row ? row.audience : "all";
    document.getElementById("st-course").value = row && row.course_id ? row.course_id : "";
    document.getElementById("st-division").value = row && row.division_id ? row.division_id : "";
    document.getElementById("st-time").value = row ? localInput(row.scheduled_at) : localInput(new Date(Date.now() + 3600000).toISOString());
    document.getElementById("st-playback").value = row ? row.playback_url : "";
    document.getElementById("st-credentials-fields").hidden = !!row;
    document.getElementById("st-ingest").value = ""; document.getElementById("st-key").value = "";
    targets(); document.getElementById("stream-dialog").showModal();
  }
  async function load() {
    var out = await TT.api("/api/admin/streams", "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    rows = out.data;
    var body = document.getElementById("streams-body");
    body.innerHTML = rows.map(function (s) {
      var audience = s.audience === "course" ? s.course_title : s.audience === "division" ? s.division_title : TT.t("notif.all");
      var actions = '<a class="btn btn-ghost btn-sm" href="/live/' + s.id + '">' + TT.t("live.watch") + '</a>';
      if (s.status === "scheduled") actions += ' <button class="btn btn-ghost btn-sm" data-edit="' + s.id + '">' + TT.t("stream.edit") + '</button> <button class="btn btn-primary btn-sm" data-status="start" data-id="' + s.id + '">' + TT.t("stream.start") + '</button>';
      if (s.status === "live") actions += ' <button class="btn btn-danger btn-sm" data-status="end" data-id="' + s.id + '">' + TT.t("stream.end") + '</button>';
      if (s.status === "scheduled" || s.status === "live") actions += ' <button class="btn btn-ghost btn-sm" data-status="cancel" data-id="' + s.id + '">' + TT.t("stream.cancel") + '</button>';
      if (TT.page.isOwner) actions += ' <button class="btn btn-ghost btn-sm" data-key="' + s.id + '">' + TT.t("stream.credentials") + '</button>';
      return '<tr><td>' + TT.esc(s.title) + '</td><td>' + TT.esc(audience) + '</td><td>' + new Date(s.scheduled_at).toLocaleString("ar-EG") + '</td><td><span class="badge badge-' + (s.status === "live" ? "approved" : "pending") + '">' + TT.t(s.status === "live" ? "live.live" : "stream." + s.status) + '</span></td><td class="row">' + actions + '</td></tr>';
    }).join("");
    body.querySelectorAll("[data-edit]").forEach(function (b) { b.addEventListener("click", function () { openForm(rows.find(function (s) { return s.id === Number(b.dataset.edit); })); }); });
    body.querySelectorAll("[data-status]").forEach(function (b) { b.addEventListener("click", async function () {
      var r = await TT.api("/api/admin/streams/" + b.dataset.id + "/status", "POST", { action: b.dataset.status });
      TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load();
    }); });
    body.querySelectorAll("[data-key]").forEach(function (b) { b.addEventListener("click", function () {
      keyStream = Number(b.dataset.key); document.getElementById("key-value").value = ""; document.getElementById("key-ingest").value = "";
      document.getElementById("key-value").type = "password"; document.getElementById("key-dialog").showModal();
    }); });
  }
  document.addEventListener("DOMContentLoaded", async function () {
    var meta = await TT.api("/api/admin/notifications/meta", "GET");
    if (meta.success) { fill(document.getElementById("st-course"), meta.data.courses, "id", "title"); fill(document.getElementById("st-division"), meta.data.divisions, "id", "name"); }
    document.getElementById("new-stream").addEventListener("click", function () { openForm(null); });
    document.getElementById("st-audience").addEventListener("change", targets);
    document.getElementById("stream-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var id = document.getElementById("stream-id").value, a = document.getElementById("st-audience").value;
      var data = { title: document.getElementById("st-title").value, description: document.getElementById("st-description").value, audience: a,
        course_id: a === "course" ? Number(document.getElementById("st-course").value) : null,
        division_id: a === "division" ? Number(document.getElementById("st-division").value) : null,
        scheduled_at: new Date(document.getElementById("st-time").value).toISOString(), playback_url: document.getElementById("st-playback").value };
      if (!id) { data.ingest_url = document.getElementById("st-ingest").value; var key = document.getElementById("st-key").value; if (key) data.publish_key = key; }
      var out = await TT.api("/api/admin/streams" + (id ? "/" + id : ""), "POST", data);
      TT.toast(out.message, out.success ? "success" : "error"); if (out.success) { document.getElementById("stream-dialog").close(); load(); }
    });
    document.getElementById("reveal-key").addEventListener("click", async function () {
      var out = await TT.api("/api/admin/streams/" + keyStream + "/credentials", "GET");
      if (!out.success) { TT.toast(out.message, "error"); return; }
      document.getElementById("key-value").value = out.data.publish_key; document.getElementById("key-value").type = "text";
      document.getElementById("key-ingest").value = out.data.ingest_url;
    });
    document.getElementById("copy-key").addEventListener("click", async function () {
      var input = document.getElementById("key-value"); input.select();
      try { await navigator.clipboard.writeText(input.value); TT.toast(TT.t("stream.copied"), "success"); } catch (e) { document.execCommand("copy"); }
    });
    var rotate = document.getElementById("rotate-key");
    if (rotate) rotate.addEventListener("click", async function () {
      var out = await TT.api("/api/admin/streams/" + keyStream + "/rotate-key", "POST", {});
      if (out.success) { document.getElementById("key-value").value = out.data.publish_key; document.getElementById("key-value").type = "text"; }
      TT.toast(out.message, out.success ? "success" : "error");
    });
    load();
  });
})();
