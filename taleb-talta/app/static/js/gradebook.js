/* Gradebook — per-course marks, totals, ranking. Export link hits the CSV endpoint. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var courseId = TT.page.courseId;
  var table = document.getElementById("gradebook-table");
  var empty = document.getElementById("gradebook-empty");

  async function load() {
    var out = await TT.api("/api/courses/" + courseId + "/gradebook", "GET");
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    var d = out.data;
    if (!d.rows.length) { empty.hidden = false; table.closest(".card").hidden = true; return; }
    var head = "<tr><th>" + L.rank + "</th><th>" + L.student + "</th><th>" + L.phone + "</th>" +
      d.exams.map(function (e) { return "<th>" + TT.esc(e.title) + "</th>"; }).join("") +
      "<th>" + L.total + "</th></tr>";
    table.querySelector("thead").innerHTML = head;
    table.querySelector("tbody").innerHTML = d.rows.map(function (r) {
      return "<tr><td>" + r.rank + "</td><td>" + TT.esc(r.name) + "</td><td dir=\"ltr\">" + TT.esc(r.phone) + "</td>" +
        d.exams.map(function (e) {
          var s = r.scores[e.id];
          return "<td>" + (s == null ? "—" : s) + "</td>";
        }).join("") +
        "<td><strong>" + r.total + "</strong></td></tr>";
    }).join("");
  }

  document.addEventListener("DOMContentLoaded", load);
})();
