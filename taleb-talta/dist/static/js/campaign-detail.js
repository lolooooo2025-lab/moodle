(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", async function () {
    var out = await TT.api("/api/campaigns/" + TT.page.campaignId, "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    var c = out.data;
    document.getElementById("campaign-article").hidden = false;
    document.getElementById("campaign-title").textContent = c.title;
    document.getElementById("campaign-week").textContent = c.week_date;
    document.getElementById("campaign-date").textContent = new Date(c.published_at).toLocaleString("ar-EG");
    document.getElementById("campaign-body").textContent = c.body;
    document.getElementById("campaign-read").hidden = c.read;
    document.getElementById("campaign-read").addEventListener("click", async function () {
      var r = await TT.api("/api/notifications/" + c.notification_id + "/read", "POST", {});
      TT.toast(r.message, r.success ? "success" : "error"); if (r.success) this.hidden = true;
    });
  });
})();
