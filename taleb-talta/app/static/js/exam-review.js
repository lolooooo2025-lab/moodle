/* Exam result review — per-question feedback, correct answer, explanation,
   and a discussion thread attached to each question. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var attemptId = TT.page.attemptId;
  var wrap = document.getElementById("review-items");

  function esc(s) { return TT.esc(s == null ? "" : String(s)); }
  function optLabel(q, i) { return (q.options && q.options[i] != null) ? q.options[i] : ""; }

  function fmtResponse(q, r) {
    if (!r) return L.notAnswered;
    if (q.qtype === "mcq_single") return r.choice == null ? L.notAnswered : esc(optLabel(q, r.choice));
    if (q.qtype === "mcq_multi") return (r.choices || []).map(function (i) { return esc(optLabel(q, i)); }).join("\u060C ") || L.notAnswered;
    if (q.qtype === "truefalse") return r.choice == null ? L.notAnswered : (r.choice ? L.true : L.false);
    if (q.qtype === "short") return esc(r.text || "") || L.notAnswered;
    if (q.qtype === "numeric") return r.value == null ? L.notAnswered : esc(r.value);
    if (q.qtype === "match") {
      var left = (q.options && q.options.left) || [], right = (q.options && q.options.right) || [];
      return (r.pairs || []).map(function (p) { return esc(left[p[0]]) + " ← " + esc(right[p[1]]); }).join("\u060C ") || L.notAnswered;
    }
    return "";
  }

  function fmtAnswer(q, a) {
    if (!a) return "";
    if (q.qtype === "mcq_single") return esc(optLabel(q, a.correct));
    if (q.qtype === "mcq_multi") return (a.correct || []).map(function (i) { return esc(optLabel(q, i)); }).join("\u060C ");
    if (q.qtype === "truefalse") return a.correct ? L.true : L.false;
    if (q.qtype === "numeric") return esc(a.value);
    if (q.qtype === "match") {
      var left = (q.options && q.options.left) || [], right = (q.options && q.options.right) || [];
      return (a.pairs || []).map(function (p) { return esc(left[p[0]]) + " ← " + esc(right[p[1]]); }).join("\u060C ");
    }
    return "";
  }

  function itemCard(it, idx) {
    var verdict = it.needs_manual
      ? '<span class="badge badge-pending">' + L.pendingManual + "</span>"
      : (it.is_correct ? '<span class="badge badge-approved">' + L.correct + "</span>"
                       : '<span class="badge badge-rejected">' + L.incorrect + "</span>");
    var answerLine = it.qtype === "short" ? "" :
      '<p class="small"><strong>' + L.correctWas + ":</strong> " + fmtAnswer(it, it.answer) + "</p>";
    var explanation = it.explanation
      ? '<div class="explanation"><strong>' + L.explanation + ":</strong><p class=\"pre-wrap m-0\">" + esc(it.explanation) + "</p></div>"
      : "";
    return '<div class="card review-item mb-2" id="question-' + it.id + '">' +
      '<div class="spread mb-1"><strong>' + L.questionN + " " + (idx + 1) + "</strong>" + verdict + "</div>" +
      '<p class="exam-prompt">' + esc(it.prompt) + "</p>" +
      '<p class="small"><strong>' + L.yourAnswer + ":</strong> " + fmtResponse(it, it.response) + "</p>" +
      answerLine + explanation +
      '<div class="mt-1 row"><button class="btn btn-ghost btn-sm" data-discuss="' + it.id + '">' + L.discuss + "</button>" +
      '<button class="btn btn-ghost btn-sm" data-forum-question="' + it.id + '">' + L.forumDiscuss + "</button>" +
      '<div class="discussion" data-panel="' + it.id + '" hidden></div></div>' +
      "</div>";
  }

  async function loadDiscussion(qid, panel) {
    panel.innerHTML = '<div class="posts" data-posts></div>' +
      '<div class="row mt-1"><input type="text" class="input-inline flex-1" data-post-input placeholder="' + L.writePost + '">' +
      '<button class="btn btn-primary btn-sm" data-post-send="' + qid + '">' + L.post + "</button></div>";
    var out = await TT.api("/api/questions/" + qid + "/posts", "GET");
    var posts = panel.querySelector("[data-posts]");
    function renderPosts(list) {
      posts.innerHTML = list.length
        ? list.map(function (p) { return '<div class="post"><strong>' + esc(p.author) + '</strong><p class="m-0">' + esc(p.body) + '</p><button class="message-report" data-report-post="' + p.id + '">' + esc(L.report) + '</button></div>'; }).join("")
        : '<p class="muted small">' + L.noPosts + "</p>";
      posts.querySelectorAll("[data-report-post]").forEach(function (btn) {
        btn.addEventListener("click", function () { TT.community.report("question_post", btn.dataset.reportPost); });
      });
    }
    renderPosts(out.success ? out.data : []);
    panel.querySelector("[data-post-send]").addEventListener("click", async function () {
      var input = panel.querySelector("[data-post-input]");
      var body = input.value.trim();
      if (!body) return;
      var res = await TT.api("/api/questions/" + qid + "/posts", "POST", { body: body });
      TT.toast(res.message, res.success ? "success" : "error");
      if (res.success) { input.value = ""; var again = await TT.api("/api/questions/" + qid + "/posts", "GET"); renderPosts(again.data); }
    });
  }

  async function load() {
    var out = await TT.api("/api/attempts/" + attemptId + "/review", "GET");
    if (!out.success) { wrap.innerHTML = '<div class="card"><p class="muted">' + esc(out.message || L.generic) + "</p></div>"; return; }
    var d = out.data;
    document.getElementById("review-score").textContent = L.score + ": " + d.score + " " + L.outOf + " " + d.max_score;
    document.getElementById("review-status").textContent = d.status === "submitted" ? L.pendingManual : "";
    wrap.innerHTML = d.items.map(itemCard).join("");
    wrap.querySelectorAll("[data-forum-question]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        btn.disabled = true;
        var out = await TT.api("/api/forum/question/" + btn.dataset.forumQuestion, "POST", { attempt_id: attemptId });
        btn.disabled = false;
        if (out.success) window.location.href = "/forum/" + out.data.id;
        else TT.toast(out.message, "error");
      });
    });
    wrap.querySelectorAll("[data-discuss]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var qid = btn.getAttribute("data-discuss");
        var panel = wrap.querySelector('[data-panel="' + qid + '"]');
        panel.hidden = !panel.hidden;
        if (!panel.hidden && !panel.dataset.loaded) { panel.dataset.loaded = "1"; loadDiscussion(qid, panel); }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", load);
})();
