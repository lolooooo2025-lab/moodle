/* Lesson player — renders content items, tracks completion, grades questions
   on the server (correct answers never reach the browser). */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var lessonId = TT.page.lessonId;
  var typeLabel = { text: L.text, file: L.file, link: L.link, question: L.question };

  function setProgress(p) {
    document.getElementById("progress-bar").style.width = p + "%";
    document.getElementById("progress-pct").textContent = p + "%";
  }

  function itemCard(it) {
    var head = '<div class="spread mb-1">' +
      '<div class="row"><span class="chip">' + (typeLabel[it.item_type] || "") + "</span>" +
      "<strong>" + TT.esc(it.title || "") + "</strong></div>" +
      '<span class="lesson-done" data-done="' + it.id + '" ' + (it.completed ? "" : "hidden") + ">✓</span></div>";
    var body = "";
    if (it.item_type === "text") {
      body = '<div class="item-body pre-wrap">' + TT.esc(it.body) + "</div>";
    } else if (it.item_type === "link") {
      body = '<a class="btn btn-ghost btn-sm" href="' + TT.esc(it.url) + '" target="_blank" rel="noopener">' +
        L.visitLink + "</a>";
    } else if (it.item_type === "file") {
      body = '<a class="btn btn-ghost btn-sm" href="/api/lesson_items/' + it.id + '/file">' +
        L.openFile + " · " + TT.esc(it.file_name || "") + "</a>";
    } else if (it.item_type === "question") {
      var opts = (it.options || []).map(function (o, i) {
        return '<label><input type="radio" name="q' + it.id + '" value="' + i + '"> ' + TT.esc(o) + "</label>";
      }).join("");
      body = '<div class="item-question"><div class="item-body pre-wrap">' +
        TT.esc(it.body) + '</div><div class="options">' + opts + "</div>" +
        '<div class="mt-1"><button class="btn btn-primary btn-sm" data-check="' + it.id + '">' +
        L.check + '</button> <span data-feedback="' + it.id + '"></span></div></div>';
    }
    var completeBtn = (it.item_type !== "question")
      ? '<div class="mt-1"><button class="btn btn-ghost btn-sm" data-complete="' + it.id + '">' +
        L.markDone + "</button></div>"
      : "";
    return '<div class="card player-item" data-item="' + it.id + '">' + head + body + completeBtn + "</div>";
  }

  function markDone(id) {
    var el = document.querySelector('[data-done="' + id + '"]');
    if (el) el.hidden = false;
    var btn = document.querySelector('[data-complete="' + id + '"]');
    if (btn) btn.disabled = true;
  }

  function bind() {
    document.querySelectorAll("[data-complete]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var id = btn.getAttribute("data-complete");
        var out = await TT.api("/api/lesson_items/" + id + "/complete", "POST", {});
        if (out.success) { markDone(id); setProgress(out.data.progress); }
        else TT.toast(out.message, "error");
      });
    });
    document.querySelectorAll("[data-check]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var id = btn.getAttribute("data-check");
        var sel = document.querySelector('input[name="q' + id + '"]:checked');
        var fb = document.querySelector('[data-feedback="' + id + '"]');
        if (!sel) return;
        var out = await TT.api("/api/lesson_items/" + id + "/check", "POST", { choice: parseInt(sel.value, 10) });
        fb.textContent = out.message;
        fb.style.color = out.data && out.data.correct ? "var(--success)" : "var(--danger)";
        if (out.data && out.data.correct) {
          markDone(id);
          var p = await TT.api("/api/lessons/" + lessonId, "GET");
          if (p.success) setProgress(p.data.progress);
        }
      });
    });
    document.getElementById("finish-btn").addEventListener("click", async function () {
      var out = await TT.api("/api/lessons/" + lessonId + "/complete", "POST", {});
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) setProgress(100);
    });
  }

  async function load() {
    var out = await TT.api("/api/lessons/" + lessonId, "GET");
    if (!out.success) {
      TT.toast(out.message || L.generic, "error");
      var player = document.querySelector(".player");
      if (player) player.innerHTML = '<div class="card empty-state"><h2>' + TT.esc(out.message || L.generic) + '</h2><a class="btn btn-primary" href="/purchases">' + TT.t("buy.my_purchases") + '</a></div>';
      return;
    }
    var d = out.data;
    document.getElementById("lesson-title").textContent = d.title;
    document.getElementById("crumb-lesson").textContent = d.title;
    var crumbCourse = document.getElementById("crumb-course");
    crumbCourse.textContent = d.course_title;
    crumbCourse.href = "/courses/" + d.course_id;
    document.getElementById("back-course").href = "/courses/" + d.course_id;
    setProgress(d.progress);
    var wrap = document.getElementById("items");
    var empty = document.getElementById("items-empty");
    if (!d.items.length) { wrap.innerHTML = ""; empty.hidden = !d.can_edit; }
    else { empty.hidden = true; wrap.innerHTML = d.items.map(itemCard).join(""); bind(); }
    if (d.can_edit) renderAddForm();
  }

  // ---- staff: add a content item ----
  function renderAddForm() {
    if (document.getElementById("add-item-card")) return;
    var card = document.createElement("div");
    card.className = "card";
    card.id = "add-item-card";
    card.style.marginTop = "20px";
    card.innerHTML = '<h3>' + L.addContent + '</h3>' +
      '<div class="field"><label>' + L.itemType + '</label>' +
      '<select id="ai-type"><option value="text">' + L.text + '</option><option value="file">' + L.file +
      '</option><option value="link">' + L.link + '</option><option value="question">' + L.question + '</option></select></div>' +
      '<div class="field"><label>' + L.itemTitle + '</label><input id="ai-title" type="text"></div>' +
      '<div class="field" data-ai="body"><label>' + L.itemBody + '</label><textarea id="ai-body"></textarea></div>' +
      '<div class="field" data-ai="url" hidden><label>' + L.itemUrl + '</label><input id="ai-url" type="url" dir="ltr"></div>' +
      '<div class="field" data-ai="file" hidden><label>' + L.itemFile + '</label><input id="ai-file" type="file"></div>' +
      '<div class="field" data-ai="options" hidden><label>' + L.qOptions + '</label><textarea id="ai-options"></textarea></div>' +
      '<div class="field" data-ai="correct" hidden><label>' + L.qCorrect + '</label><input id="ai-correct" type="number" min="1" value="1"></div>' +
      '<button class="btn btn-primary" id="ai-submit">' + L.addItem + '</button>';
    document.querySelector(".player").insertBefore(card, document.querySelector(".player-nav"));
    var typeSel = document.getElementById("ai-type");
    function sync() {
      var t = typeSel.value;
      card.querySelector('[data-ai="body"]').hidden = !(t === "text" || t === "question");
      card.querySelector('[data-ai="url"]').hidden = t !== "link";
      card.querySelector('[data-ai="file"]').hidden = t !== "file";
      card.querySelector('[data-ai="options"]').hidden = t !== "question";
      card.querySelector('[data-ai="correct"]').hidden = t !== "question";
    }
    typeSel.addEventListener("change", sync); sync();
    document.getElementById("ai-submit").addEventListener("click", async function () {
      var t = typeSel.value;
      var fd = new FormData();
      fd.append("item_type", t);
      fd.append("title", document.getElementById("ai-title").value);
      fd.append("body", document.getElementById("ai-body").value);
      fd.append("url", document.getElementById("ai-url").value);
      if (t === "file" && document.getElementById("ai-file").files[0]) {
        fd.append("upload", document.getElementById("ai-file").files[0]);
      }
      if (t === "question") {
        fd.append("options", document.getElementById("ai-options").value);
        fd.append("correct_index", parseInt(document.getElementById("ai-correct").value, 10) - 1);
      }
      var out = await TT.upload("/api/lessons/" + lessonId + "/items", fd);
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) setTimeout(function () { location.reload(); }, 600);
    });
  }

  document.addEventListener("DOMContentLoaded", load);
})();
