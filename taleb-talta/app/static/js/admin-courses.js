/* Admin course management — create course/category, delete, list categories. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};

  function val(form, name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? el.value : "";
  }
  function nullableInt(v) { return v === "" ? null : parseInt(v, 10); }

  async function loadCats() {
    var out = await TT.api("/api/categories", "GET");
    var wrap = document.getElementById("cat-list");
    if (!out.success) return;
    wrap.innerHTML = out.data.map(function (c) {
      return '<span class="chip">' + TT.esc(c.name) + "</span>";
    }).join("");
  }

  var courseFields = [], editingCourse = 0;
  document.addEventListener("DOMContentLoaded", async function () {
    loadCats();
    var cf = await TT.api("/api/custom-fields/course", "GET");
    courseFields = cf.success ? cf.data : [];
    TTCustomFields.render(document.getElementById("course-custom-fields"), courseFields, {}, "course-cf");

    document.getElementById("course-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var f = ev.target;
      var errBox = f.querySelector(".form-error");
      errBox.hidden = true;
      var body = {
        title: val(f, "title"), summary: val(f, "summary"),
        category_id: nullableInt(val(f, "category_id")),
        division_id: nullableInt(val(f, "division_id")),
        visibility: val(f, "visibility"),
        custom_fields: TTCustomFields.collect(document.getElementById("course-custom-fields"))
      };
      var out = await TT.api("/api/courses", "POST", body);
      if (out.success) { TT.toast(out.message, "success"); setTimeout(function () { location.reload(); }, 600); }
      else { errBox.textContent = out.message; errBox.hidden = false; }
    });

    document.getElementById("category-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var f = ev.target;
      var out = await TT.api("/api/categories", "POST", { name: val(f, "name") });
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) { f.reset(); loadCats(); setTimeout(function () { location.reload(); }, 600); }
    });

    document.querySelectorAll("[data-course-fields]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        editingCourse = parseInt(btn.getAttribute("data-course-fields"), 10);
        var out = await TT.api("/api/custom-fields/course/" + editingCourse + "/values", "GET");
        TTCustomFields.render(document.getElementById("course-fields-values"), courseFields, out.success ? out.data : {}, "edit-course-cf");
        document.getElementById("course-fields-form").querySelector(".form-error").hidden = true;
        document.getElementById("course-fields-dialog").showModal();
      });
    });
    document.getElementById("course-fields-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var out = await TT.api("/api/custom-fields/course/" + editingCourse + "/values", "POST", { values: TTCustomFields.collect(document.getElementById("course-fields-values")) });
      if (out.success) { document.getElementById("course-fields-dialog").close(); TT.toast(out.message, "success"); }
      else { var e = ev.target.querySelector(".form-error"); e.textContent = out.message; e.hidden = false; }
    });
    document.querySelectorAll("[data-delete]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        if (!window.confirm(L.confirmDelete)) return;
        var out = await TT.api("/api/courses/" + btn.getAttribute("data-delete") + "/delete", "POST", {});
        TT.toast(out.message, out.success ? "success" : "error");
        if (out.success) setTimeout(function () { location.reload(); }, 600);
      });
    });
  });
})();
