/* Forum index: create a general/course thread and browse authorised discussions. */
(function () {
  "use strict";
  var L = TT.labels;
  var list = document.getElementById("forum-list");
  var panel = document.getElementById("new-thread-panel");
  var form = document.getElementById("new-thread-form");
  var scope = document.getElementById("thread-scope");
  function row(t) {
    var kind = t.question_id ? L.question : (t.course_id ? L.course : L.general);
    return '<article class="card thread-row"><div class="thread-mark">' + TT.esc(kind.charAt(0)) + '</div>' +
      '<div class="flex-1"><div class="row mb-1"><span class="chip">' + TT.esc(kind) + '</span>' +
      (t.locked ? '<span class="badge">' + TT.esc(L.locked) + '</span>' : '') +
      (t.unread ? '<span class="badge badge-approved">' + TT.esc(L.unread) + ' ' + t.unread + '</span>' : '') + '</div>' +
      '<h3 class="m-0"><a class="thread-link" href="/forum/' + t.id + '">' + TT.esc(t.title) + '</a></h3>' +
      '<p class="muted small">' + TT.esc(L.by) + ' ' + TT.esc(t.author) + ' · ' + TT.community.fmtDate(t.created_at) + '</p></div>' +
      '<span class="thread-count"><strong>' + t.post_count + '</strong><span class="muted small">' + TT.esc(L.posts) + '</span></span></article>';
  }
  async function load() {
    try {
      var courseId = new URLSearchParams(window.location.search).get("course_id");
      var out = await TT.api("/api/forum/threads" + (courseId ? "?course_id=" + encodeURIComponent(courseId) : ""), "GET");
      if (!out.success) { list.innerHTML = '<p class="alert alert-warning">' + TT.esc(out.message) + '</p>'; return; }
      list.innerHTML = out.data.map(row).join("");
      document.getElementById("forum-empty").hidden = out.data.length > 0;
    } catch (e) { list.innerHTML = '<p class="alert alert-warning">' + TT.esc(L.generic) + '</p>'; }
  }
  document.addEventListener("DOMContentLoaded", async function () {
    document.getElementById("refresh-forum").addEventListener("click", load);
    var open = document.getElementById("new-thread-btn");
    if (open) open.addEventListener("click", function () { panel.hidden = !panel.hidden; if (!panel.hidden) document.getElementById("thread-title").focus(); });
    document.getElementById("cancel-thread").addEventListener("click", function () { panel.hidden = true; });
    if (form) form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var btn = form.querySelector('[type="submit"]'); btn.disabled = true;
      try {
        var out = await TT.api("/api/forum/threads", "POST", { title: document.getElementById("thread-title").value.trim(), body: document.getElementById("thread-body").value.trim(), course_id: scope.value ? Number(scope.value) : null });
        TT.toast(out.message || L.generic, out.success ? "success" : "error");
        if (out.success) window.location.href = "/forum/" + out.data.id;
      } catch (e) { TT.toast(L.generic, "error"); }
      finally { btn.disabled = false; }
    });
    await load();
    try {
      var courses = await TT.api("/api/courses", "GET");
      if (courses.success) courses.data.forEach(function (c) {
        if (!c.enrolled && !(TT.page && TT.page.canManageCourse)) return;
        var o = document.createElement("option"); o.value = c.id; o.textContent = c.title; scope.appendChild(o);
      });
    } catch (e) {}
  });
})();
