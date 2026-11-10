/* Courses list — fetches /api/courses, renders cards, handles enrolment. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var grid = document.getElementById("courses-grid");
  var empty = document.getElementById("courses-empty");
  var catFilter = document.getElementById("cat-filter");
  var search = document.getElementById("course-search");
  var all = [];
  var catNames = {};

  function card(c) {
    var enrolled = c.enrolled;
    var action = c.can_learn || enrolled
      ? '<a class="btn btn-primary btn-sm" href="/courses/' + c.id + '">' + L.open + "</a>"
      : c.price_cents > 0
        ? '<a class="btn btn-accent btn-sm" href="/courses/' + c.id + '">' + L.buy + "</a>"
        : '<button class="btn btn-accent btn-sm" data-enrol="' + c.id + '">' + L.enroll + "</button>";
    var price = c.price_cents > 0
      ? '<span class="badge badge-pending">' + L.paid + " · " + TT.esc(new Intl.NumberFormat("ar-EG", { style: "currency", currency: "EGP" }).format(c.price_cents / 100)) + "</span>"
      : '<span class="badge badge-approved">' + L.free + "</span>";
    var div = c.division_name ? '<span class="badge">' + TT.esc(c.division_name) + "</span>" : "";
    var lessons = (L.lessons || "{n}").replace("{n}", c.lesson_count);
    return '<div class="card course-card">' +
      '<div class="course-meta"><span class="chip">' + TT.esc(c.category_name || "—") + "</span>" + div + price + "</div>" +
      "<h3>" + TT.esc(c.title) + "</h3>" +
      '<p class="course-desc">' + TT.esc(c.summary || "") + "</p>" +
      '<div class="spread"><span class="muted small">' + TT.esc(lessons) + "</span>" + action + "</div>" +
      "</div>";
  }

  function render() {
    var cat = catFilter.value;
    var q = (search.value || "").trim();
    var rows = all.filter(function (c) {
      if (cat && String(c.category_name) !== catNames[cat]) return false;
      if (q && c.title.indexOf(q) === -1) return false;
      return true;
    });
    grid.innerHTML = rows.map(card).join("");
    empty.hidden = rows.length > 0;
    grid.querySelectorAll("[data-enrol]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        btn.disabled = true;
        var out = await TT.api("/api/courses/" + btn.getAttribute("data-enrol") + "/enrol", "POST", {});
        TT.toast(out.message, out.success ? "success" : "error");
        if (out.success) load(); else btn.disabled = false;
      });
    });
  }

  async function load() {
    var out = await TT.api("/api/courses", "GET");
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    all = out.data;
    render();
  }

  document.addEventListener("DOMContentLoaded", async function () {
    var cats = await TT.api("/api/categories", "GET");
    if (cats.success) {
      cats.data.forEach(function (c) {
        catNames[c.id] = c.name;
        var o = document.createElement("option");
        o.value = c.id; o.textContent = c.name;
        catFilter.appendChild(o);
      });
    }
    catFilter.addEventListener("change", render);
    search.addEventListener("input", render);
    load();
  });
})();
