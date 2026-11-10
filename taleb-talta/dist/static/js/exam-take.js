/* Exam runner — start attempt, render questions by type, timer, submit to server.
   Correct answers never arrive here; grading happens server-side. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var examId = TT.page.examId;
  var attemptId = null;
  var timerHandle = null;
  var submitted = false;

  var intro = document.getElementById("exam-intro");
  var runner = document.getElementById("exam-runner");
  var result = document.getElementById("exam-result");
  var form = document.getElementById("exam-form");

  function esc(s) { return TT.esc(s == null ? "" : String(s)); }

  // ---- intro ----
  async function loadIntro() {
    var out = await TT.api("/api/exams/" + examId, "GET");
    if (!out.success) {
      var e = document.getElementById("intro-error");
      e.textContent = out.message || L.generic; e.hidden = false;
      document.getElementById("start-btn").hidden = true;
      return;
    }
    var d = out.data;
    document.getElementById("exam-title").textContent = d.title;
    document.getElementById("crumb-title").textContent = d.title;
    document.getElementById("exam-desc").textContent = d.description || "";
    var meta = '<span class="chip">' + L.questions + ": " + d.questions.length + "</span>";
    if (d.time_limit_minutes > 0) meta += '<span class="badge">' + L.minutes + ": " + d.time_limit_minutes + "</span>";
    meta += '<span class="badge">' + L.attempts + ": " + (d.max_attempts === 0 ? "∞" : d.max_attempts) + "</span>";
    document.getElementById("exam-meta").innerHTML = meta;
  }

  // ---- question rendering ----
  function optionsHtml(q) {
    var opts = q.options || [];
    if (q.qtype === "mcq_single") {
      return opts.map(function (o, i) {
        return '<label class="option-row"><input type="radio" name="q' + q.id + '" value="' + i + '"> ' + esc(o) + "</label>";
      }).join("");
    }
    if (q.qtype === "mcq_multi") {
      return '<p class="muted small">' + L.chooseMulti + "</p>" + opts.map(function (o, i) {
        return '<label class="option-row"><input type="checkbox" name="q' + q.id + '" value="' + i + '"> ' + esc(o) + "</label>";
      }).join("");
    }
    if (q.qtype === "truefalse") {
      return '<label class="option-row"><input type="radio" name="q' + q.id + '" value="true"> ' + L.true + "</label>" +
             '<label class="option-row"><input type="radio" name="q' + q.id + '" value="false"> ' + L.false + "</label>";
    }
    if (q.qtype === "short") {
      return '<textarea name="q' + q.id + '" placeholder="' + L.shortAnswer + '"></textarea>';
    }
    if (q.qtype === "numeric") {
      return '<input type="number" step="any" name="q' + q.id + '" placeholder="' + L.numeric + '" dir="ltr">';
    }
    if (q.qtype === "match") {
      var left = (q.options && q.options.left) || [];
      var right = (q.options && q.options.right) || [];
      return left.map(function (l, i) {
        var sel = '<select data-match="' + i + '"><option value="">—</option>' +
          right.map(function (r, j) { return '<option value="' + j + '">' + esc(r) + "</option>"; }).join("") + "</select>";
        return '<div class="match-row"><span>' + esc(l) + "</span>" + sel + "</div>";
      }).join("");
    }
    return "";
  }

  function renderQuestions(questions) {
    form.innerHTML = questions.map(function (q, idx) {
      return '<div class="card exam-question mb-2" data-qid="' + q.id + '" data-qtype="' + q.qtype + '">' +
        '<div class="spread mb-1"><strong>' + L.questionN + " " + (idx + 1) + "</strong>" +
        '<span class="chip">' + L.points + ": " + q.points + "</span></div>" +
        '<p class="exam-prompt">' + esc(q.prompt) + "</p>" +
        optionsHtml(q) + "</div>";
    }).join("");
  }

  function collect() {
    var answers = {};
    form.querySelectorAll(".exam-question").forEach(function (block) {
      var qid = block.getAttribute("data-qid");
      var type = block.getAttribute("data-qtype");
      if (type === "mcq_single") {
        var c = block.querySelector("input[type=radio]:checked");
        answers[qid] = { choice: c ? parseInt(c.value, 10) : null };
      } else if (type === "mcq_multi") {
        answers[qid] = { choices: Array.prototype.map.call(block.querySelectorAll("input[type=checkbox]:checked"),
          function (x) { return parseInt(x.value, 10); }) };
      } else if (type === "truefalse") {
        var t = block.querySelector("input[type=radio]:checked");
        answers[qid] = { choice: t ? t.value === "true" : null };
      } else if (type === "short") {
        answers[qid] = { text: block.querySelector("textarea").value };
      } else if (type === "numeric") {
        var v = block.querySelector("input[type=number]").value;
        answers[qid] = { value: v === "" ? null : parseFloat(v) };
      } else if (type === "match") {
        var pairs = [];
        block.querySelectorAll("[data-match]").forEach(function (sel) {
          if (sel.value !== "") pairs.push([parseInt(sel.getAttribute("data-match"), 10), parseInt(sel.value, 10)]);
        });
        answers[qid] = { pairs: pairs };
      }
    });
    return answers;
  }

  // ---- timer ----
  function startTimer(expiresAt) {
    if (!expiresAt) return;
    var timer = document.getElementById("timer");
    timer.hidden = false;
    var end = new Date(expiresAt).getTime();
    function tick() {
      var left = Math.max(0, Math.floor((end - Date.now()) / 1000));
      var m = Math.floor(left / 60), s = left % 60;
      timer.textContent = L.timeLeft + ": " + m + ":" + (s < 10 ? "0" : "") + s;
      if (left <= 0) { clearInterval(timerHandle); doSubmit(true); }
    }
    tick();
    timerHandle = setInterval(tick, 1000);
  }

  // ---- start + submit ----
  async function start() {
    var out = await TT.api("/api/exams/" + examId + "/start", "POST", {});
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    var d = out.data;
    attemptId = d.attempt_id;
    intro.hidden = true;
    runner.hidden = false;
    document.getElementById("runner-title").textContent = d.title;
    renderQuestions(d.questions);
    startTimer(d.expires_at);
    window.scrollTo(0, 0);
  }

  async function doSubmit(auto) {
    if (submitted || !attemptId) return;
    if (!auto && !window.confirm(L.confirmSubmit)) return;
    submitted = true;
    if (timerHandle) clearInterval(timerHandle);
    var out = await TT.api("/api/attempts/" + attemptId + "/submit", "POST", { answers: collect() });
    if (!out.success) {
      submitted = false;
      TT.toast(out.message || L.generic, "error");
      return;
    }
    var d = out.data;
    runner.hidden = true;
    result.hidden = false;
    document.getElementById("result-score").textContent = L.score + ": " + d.score + " " + L.outOf + " " + d.max_score;
    document.getElementById("result-note").textContent = d.needs_manual ? L.pendingManual : "";
    document.getElementById("review-link").href = "/attempts/" + d.attempt_id + "/review";
    window.scrollTo(0, 0);
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadIntro();
    document.getElementById("start-btn").addEventListener("click", start);
    document.getElementById("submit-btn").addEventListener("click", function () { doSubmit(false); });
  });
})();
