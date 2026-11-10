/* Exams list — pick a course, list its exams, link to take/review/gradebook. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var grid = document.getElementById("exams-grid");
  var empty = document.getElementById("exams-empty");
  var sel = document.getElementById("exam-course");

  function card(e) {
    var meta = '<span class="chip">' + (L.questions || "") + ": " + e.question_count + "</span>";
    if (e.time_limit_minutes > 0) {
      meta += '<span class="badge">' + e.time_limit_minutes + " " + (L.minutes || "") + "</span>";
    }
    var stats = '<span class="muted small">' + (L.attempts || "") + ": " + e.attempts_used;
    if (e.best_score !== null && e.best_score !== undefined) {
      stats += " · " + (L.best || "") + ": " + e.best_score;
    }
    stats += "</span>";
    var action = '<a class="btn btn-primary btn-sm" href="/exams/' + e.id + '">' + (L.start || "") + "</a>";
    return '<div class="card course-card">' +
      '<div class="course-meta">' + meta + "</div>" +
      "<h3>" + TT.esc(e.title) + "</h3>" +
      '<p class="course-desc">' + TT.esc(e.description || "") + "</p>" +
      '<div class="spread">' + stats + action + "</div>" +
      "</div>";
  }

  async function loadExams() {
    var cid = sel.value;
    if (!cid) { grid.innerHTML = ""; empty.hidden = false; return; }
    var out = await TT.api("/api/exams?course_id=" + cid, "GET");
    if (!out.success) { grid.innerHTML = ""; empty.hidden = false; return; }
    var rows = out.data;
    grid.innerHTML = rows.map(card).join("");
    empty.hidden = rows.length > 0;
  }

  document.addEventListener("DOMContentLoaded", async function () {
    var courses = await TT.api("/api/courses", "GET");
    if (courses.success) {
      courses.data.forEach(function (c) {
        var o = document.createElement("option");
        o.value = c.id; o.textContent = c.title;
        sel.appendChild(o);
      });
    }
    sel.addEventListener("change", loadExams);
    if (sel.value) loadExams();
  });
})();
