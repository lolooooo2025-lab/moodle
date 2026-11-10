/* Thread detail: nested replies, explicit read marker, subscription and reports. */
(function () {
  "use strict";
  var L = TT.labels, id = TT.page.threadId, data = null, parentId = null;
  var posts = document.getElementById("thread-posts");
  var form = document.getElementById("reply-form");
  function post(p) {
    return '<article id="post-' + p.id + '" class="card forum-post' + (p.parent_id ? ' reply-child' : '') + '">' +
      '<div class="spread mb-1"><strong>' + TT.esc(p.author) + '</strong><time class="muted small">' + TT.community.fmtDate(p.created_at) + '</time></div>' +
      '<p class="pre-wrap m-0">' + TT.esc(p.body) + '</p><div class="row mt-1">' +
      (data.can_post && !data.locked && !data.restricted ? '<button class="btn btn-ghost btn-sm" data-reply="' + p.id + '" data-author="' + TT.esc(p.author) + '">' + TT.esc(L.reply) + '</button>' : '') +
      (p.author_id !== TT.page.userId ? '<button class="btn btn-ghost btn-sm" data-report="' + p.id + '">' + TT.esc(L.report) + '</button>' : '') + '</div></article>';
  }
  async function load() {
    try {
      var out = await TT.api("/api/forum/threads/" + id, "GET");
      if (!out.success) { document.getElementById("thread-title").textContent = out.message; posts.innerHTML = ""; return; }
      data = out.data;
      document.getElementById("thread-title").textContent = data.title;
      document.getElementById("thread-meta").textContent = L.by + " " + data.author + " · " + TT.community.fmtDate(data.created_at);
      document.getElementById("thread-state").hidden = !data.locked;
      document.getElementById("subscribe-btn").textContent = data.subscribed ? L.unsubscribe : L.subscribe;
      var lock = document.getElementById("lock-btn"); lock.hidden = !data.can_moderate; lock.textContent = data.locked ? L.unlock : L.lock;
      posts.innerHTML = data.posts.length ? data.posts.map(post).join("") : '<p class="card muted">' + TT.esc(L.empty) + '</p>';
      if (data.exam_id) {
        var link = document.createElement("a"); link.className = "chip"; link.href = "/exams/" + data.exam_id; link.textContent = L.backExam;
        document.getElementById("thread-meta").appendChild(document.createTextNode(" ")); document.getElementById("thread-meta").appendChild(link);
      }
      document.getElementById("reply-panel").hidden = !data.can_post || (data.locked && !data.can_moderate);
      document.getElementById("restriction-notice").hidden = !data.restricted;
      form.querySelector('[type="submit"]').disabled = data.restricted;
      posts.querySelectorAll("[data-reply]").forEach(function (btn) { btn.addEventListener("click", function () {
        parentId = Number(btn.dataset.reply);
        document.getElementById("reply-heading").textContent = L.replyTo + " " + btn.dataset.author;
        document.getElementById("cancel-reply").hidden = false;
        document.getElementById("reply-body").focus();
      }); });
      posts.querySelectorAll("[data-report]").forEach(function (btn) { btn.addEventListener("click", function () { TT.community.report("forum_post", btn.dataset.report); }); });
      await TT.api("/api/forum/threads/" + id + "/read", "POST", {});
      if (window.location.hash) { var target = document.querySelector(window.location.hash); if (target) target.scrollIntoView(); }
    } catch (e) { TT.toast(L.generic, "error"); }
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("refresh-thread").addEventListener("click", load);
    document.getElementById("cancel-reply").addEventListener("click", function () {
      parentId = null; document.getElementById("reply-heading").textContent = L.reply; this.hidden = true;
    });
    document.getElementById("subscribe-btn").addEventListener("click", async function () {
      var out = await TT.api("/api/forum/threads/" + id + "/subscribe", "POST", {});
      TT.toast(out.message, out.success ? "success" : "error"); if (out.success) load();
    });
    document.getElementById("lock-btn").addEventListener("click", async function () {
      var out = await TT.api("/api/forum/threads/" + id + "/lock", "POST", { locked: !data.locked });
      TT.toast(out.message, out.success ? "success" : "error"); if (out.success) load();
    });
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var input = document.getElementById("reply-body"), body = input.value.trim(); if (!body) return;
      var btn = form.querySelector('[type="submit"]'); btn.disabled = true;
      try {
        var out = await TT.api("/api/forum/threads/" + id + "/posts", "POST", { body: body, parent_id: parentId });
        TT.toast(out.message || L.generic, out.success ? "success" : "error");
        if (out.success) { input.value = ""; parentId = null; document.getElementById("cancel-reply").click(); await load(); }
      } catch (e) { TT.toast(L.generic, "error"); }
      finally { btn.disabled = data ? data.restricted : false; }
    });
    load();
  });
})();
