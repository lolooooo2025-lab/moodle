(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", async function () {
    var out = await TT.api("/api/campaigns", "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    document.getElementById("campaigns-empty").hidden = out.data.length > 0;
    document.getElementById("campaign-list").innerHTML = out.data.map(function (c) {
      return '<article class="card"><div class="spread"><h2 class="m-0">' + TT.esc(c.title) + '</h2><span class="badge badge-approved" dir="ltr">' + c.week_date + '</span></div><p class="pre-wrap">' + TT.esc(c.body) + '</p><a class="btn btn-ghost btn-sm" href="/campaigns/' + c.id + '">' + TT.t("nav.open") + '</a></article>';
    }).join("");
  });
})();
