/* Owner-only security policy editor. */
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", async function () {
    var form = document.getElementById("security-form"), box = document.getElementById("security-fields");
    var out = await TT.api("/api/admin/security", "GET");
    if (!out.success) return TT.toast(out.message, "error");
    box.innerHTML = Object.keys(out.data.specs).map(function (k) {
      var s = out.data.specs[k];
      return '<div class="field"><label for="sec-' + k + '">' + TT.esc(TT.t("settings." + k.replace("security.", ""))) + '</label><input id="sec-' + k + '" name="' + k + '" type="number" dir="ltr" min="' + s.min + '" max="' + s.max + '" value="' + TT.esc(out.data.values[k]) + '" required></div>';
    }).join("");
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var values = {}; new FormData(form).forEach(function (v, k) { values[k] = parseInt(v, 10); });
      var res = await TT.api("/api/admin/security", "POST", { values: values });
      var err = form.querySelector(".form-error"); err.hidden = res.success; err.textContent = res.message;
      TT.toast(res.message, res.success ? "success" : "error");
    });
  });
})();
