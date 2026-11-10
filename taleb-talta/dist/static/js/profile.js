/* Self-service profile + custom fields. Core identity stays support-only. */
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", async function () {
    var form = document.getElementById("profile-form");
    var box = document.getElementById("profile-custom-fields");
    var out = await TT.api("/api/users/me/custom-fields", "GET");
    if (out.success) TTCustomFields.render(box, out.data.fields, out.data.values, "profile-cf");
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var err = form.querySelector(".form-error"); err.hidden = true;
      var data = new FormData(form);
      var body = { name: data.get("name") || "", title: data.get("title") || "", badge: data.get("badge") || "", custom_fields: TTCustomFields.collect(box) };
      var res = await TT.api("/api/users/profile", "POST", body);
      TT.toast(res.message, res.success ? "success" : "error");
      if (!res.success) { err.textContent = res.message; err.hidden = false; }
    });
  });
})();
