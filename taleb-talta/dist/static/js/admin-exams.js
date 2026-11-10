/* Admin exams — question bank editor (6 types) + exam builder + add questions. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var courseSel = document.getElementById("admin-course");
  var qList = document.getElementById("question-list");
  var eList = document.getElementById("exam-list");
  var bank = [];

  function esc(s) { return TT.esc(s == null ? "" : String(s)); }
  function lines(id) {
    return document.getElementById(id).value.split("\n").map(function (x) { return x.trim(); })
      .filter(function (x) { return x !== ""; });
  }
  function courseId() { return courseSel.value; }

  // ---- question type field visibility ----
  var qType = document.getElementById("q-type");
  function syncType() {
    var t = qType.value;
    function show(key, on) { document.querySelector('[data-q="' + key + '"]').hidden = !on; }
    show("options", t === "mcq_single" || t === "mcq_multi");
    show("answer", t === "mcq_single" || t === "mcq_multi");
    show("tf", t === "truefalse");
    show("numvalue", t === "numeric");
    show("numtol", t === "numeric");
    show("matchleft", t === "match");
    show("matchright", t === "match");
    show("matchpairs", t === "match");
  }
  qType.addEventListener("change", syncType);

  function buildQuestion() {
    var t = qType.value;
    var payload = { course_id: parseInt(courseId(), 10), qtype: t,
      prompt: document.getElementById("q-prompt").value,
      explanation: document.getElementById("q-explanation").value };
    if (t === "mcq_single" || t === "mcq_multi") {
      payload.options_json = lines("q-options");
      var raw = document.getElementById("q-answer").value.trim();
      if (t === "mcq_single") {
        payload.answer_json = { correct: parseInt(raw, 10) - 1 };
      } else {
        payload.answer_json = { correct: raw.split(",").map(function (x) { return parseInt(x.trim(), 10) - 1; })
          .filter(function (x) { return !isNaN(x); }) };
      }
    } else if (t === "truefalse") {
      payload.answer_json = { correct: document.getElementById("q-tf").value === "true" };
    } else if (t === "numeric") {
      payload.answer_json = { value: parseFloat(document.getElementById("q-numvalue").value),
        tolerance: parseFloat(document.getElementById("q-numtol").value) || 0 };
    } else if (t === "match") {
      payload.options_json = { left: lines("q-matchleft"), right: lines("q-matchright") };
      payload.answer_json = { pairs: lines("q-matchpairs").map(function (ln) {
        var p = ln.split(":"); return [parseInt(p[0], 10) - 1, parseInt(p[1], 10) - 1]; }) };
    }
    return payload;
  }

  // ---- question bank ----
  function renderBank() {
    if (!bank.length) { qList.innerHTML = '<p class="muted small">' + L.noBank + "</p>"; return; }
    qList.innerHTML = bank.map(function (q) {
      return '<div class="bank-row spread">' +
        '<span><span class="chip">' + esc((L.typeLabels || {})[q.qtype] || q.qtype) + "</span> " + esc(q.prompt) + "</span>" +
        '<button class="btn btn-ghost btn-sm" data-delq="' + q.id + '" aria-label="' + L.deleteQuestion + '">×</button>' +
        "</div>";
    }).join("");
    qList.querySelectorAll("[data-delq]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var out = await TT.api("/api/questions/" + b.getAttribute("data-delq") + "/delete", "POST", {});
        TT.toast(out.message, out.success ? "success" : "error");
        if (out.success) loadAll();
      });
    });
  }

  // ---- exams ----
  function examCard(e) {
    var opts = bank.map(function (q) { return '<option value="' + q.id + '">' + esc(q.prompt.slice(0, 60)) + "</option>"; }).join("");
    return '<div class="card exam-admin-card mb-1">' +
      '<div class="spread"><strong>' + esc(e.title) + '</strong><span class="chip">' + L.questions + ": " + e.question_count + "</span></div>" +
      '<div class="row mt-1">' +
      '<select class="input-inline flex-1" data-pick="' + e.id + '"><option value="">' + L.pickQuestion + "</option>" + opts + "</select>" +
      '<input class="input-inline w-140" type="number" min="1" value="1" data-points="' + e.id + '" aria-label="' + L.points + '">' +
      '<button class="btn btn-primary btn-sm" data-addq="' + e.id + '">' + L.addToExam + "</button>" +
      "</div>" +
      '<div class="mt-1"><a class="btn btn-ghost btn-sm" href="/courses/' + courseId() + '/gradebook">' + L.gradebook + "</a></div>" +
      "</div>";
  }

  function renderExams(exams) {
    if (!exams.length) { eList.innerHTML = '<p class="muted small">' + L.noExams + "</p>"; return; }
    eList.innerHTML = exams.map(examCard).join("");
    eList.querySelectorAll("[data-addq]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var eid = b.getAttribute("data-addq");
        var qid = eList.querySelector('[data-pick="' + eid + '"]').value;
        var pts = parseInt(eList.querySelector('[data-points="' + eid + '"]').value, 10) || 1;
        if (!qid) return;
        var out = await TT.api("/api/exams/" + eid + "/questions", "POST", { question_id: parseInt(qid, 10), points: pts });
        TT.toast(out.message, out.success ? "success" : "error");
        if (out.success) loadAll();
      });
    });
  }

  async function loadAll() {
    if (!courseId()) return;
    var qs = await TT.api("/api/questions?course_id=" + courseId(), "GET");
    bank = qs.success ? qs.data : [];
    renderBank();
    var es = await TT.api("/api/exams?course_id=" + courseId(), "GET");
    renderExams(es.success ? es.data : []);
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncType();
    courseSel.addEventListener("change", loadAll);
    document.getElementById("question-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var out = await TT.api("/api/questions", "POST", buildQuestion());
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) { document.getElementById("q-prompt").value = ""; loadAll(); }
    });
    document.getElementById("exam-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var out = await TT.api("/api/exams", "POST", {
        course_id: parseInt(courseId(), 10),
        title: document.getElementById("e-title").value,
        description: document.getElementById("e-desc").value,
        time_limit_minutes: parseInt(document.getElementById("e-time").value, 10) || 0,
        max_attempts: parseInt(document.getElementById("e-attempts").value, 10) || 0
      });
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) { document.getElementById("e-title").value = ""; loadAll(); }
    });
    loadAll();
  });
})();
