/* Typed plugin settings dialog. */
(function () {
  "use strict";
  var component = "";
  document.addEventListener("DOMContentLoaded", function () {
    var dialog = document.getElementById("plugin-settings-dialog"), form = document.getElementById("plugin-settings-form");
    document.querySelectorAll("[data-plugin-settings]").forEach(function (b) { b.addEventListener("click", async function () {
      component = b.getAttribute("data-plugin-settings");
      var out = await TT.api("/api/plugins/" + component + "/settings", "GET");
      if (!out.success) return TT.toast(out.message, "error");
      document.getElementById("plugin-settings-title").textContent = TT.t("admin.plugin_settings") + " · " + component;
      document.getElementById("plugin-settings-fields").innerHTML = out.data.map(function (s) {
        var id = "ps-" + s.name;
        if (s.type === "bool") return '<label class="check-row"><input id="' + id + '" name="' + TT.esc(s.name) + '" type="checkbox" ' + (s.value === "1" ? "checked" : "") + '> ' + TT.esc(TT.t(s.label_key)) + '</label>';
        return '<div class="field"><label for="' + id + '">' + TT.esc(TT.t(s.label_key)) + '</label><input id="' + id + '" name="' + TT.esc(s.name) + '" type="' + (s.type === "int" ? "number" : "text") + '" value="' + TT.esc(s.value) + '" ' + (s.type === "int" ? 'min="' + s.min + '" max="' + s.max + '" dir="ltr"' : '') + '></div>';
      }).join("");
      form.querySelector(".form-error").hidden = true;
      dialog.showModal();
    }); });
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault(); var values = {};
      form.querySelectorAll("[name]").forEach(function (el) { values[el.name] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value; });
      var out = await TT.api("/api/plugins/" + component + "/settings", "POST", { values: values });
      if (out.success) { dialog.close(); TT.toast(out.message, "success"); }
      else { var e = form.querySelector(".form-error"); e.textContent = out.message; e.hidden = false; }
    });
  });
})();
