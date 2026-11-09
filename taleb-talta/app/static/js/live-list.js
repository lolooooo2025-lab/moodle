(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", async function () {
    var out = await TT.api("/api/streams", "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    document.getElementById("live-empty").hidden = out.data.length > 0;
    document.getElementById("live-list").innerHTML = out.data.map(function (s) {
      var audience = s.audience === "course" ? s.course_title : s.audience === "division" ? s.division_title : TT.t("notif.all");
      return '<article class="card"><div class="spread"><h2 class="m-0">' + TT.esc(s.title) + '</h2><span class="badge badge-' + (s.status === "live" ? "approved" : "pending") + '">' + TT.t(s.status === "live" ? "live.live" : "live." + s.status) + '</span></div><p class="muted">' + TT.esc(audience) + '</p><p class="muted small">' + new Date(s.scheduled_at).toLocaleString("ar-EG") + '</p><p class="pre-wrap">' + TT.esc(s.description) + '</p><a class="btn btn-primary btn-sm" href="/live/' + s.id + '">' + TT.t("live.watch") + '</a></article>';
    }).join("");
  });
})();
