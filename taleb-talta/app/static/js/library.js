/* Library — shared list, private space, upload, and offline copies (IndexedDB). */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};

  // ---- tabs ----
  function switchTab(name) {
    ["shared", "private", "upload"].forEach(function (n) {
      document.getElementById("tab-" + n).hidden = (n !== name);
    });
    document.querySelectorAll("[data-tab]").forEach(function (b) {
      var active = b.getAttribute("data-tab") === name;
      b.className = "btn btn-sm " + (active ? "btn-primary" : "btn-ghost");
    });
    if (name === "shared") loadShared();
    if (name === "private") loadPrivate();
  }

  // ---- shared ----
  function sharedCard(it) {
    var saveBtn = it.saved
      ? '<span class="badge badge-approved">' + L.saved + "</span>"
      : '<button class="btn btn-ghost btn-sm" data-save="' + it.id + '">' + L.save + "</button>";
    var dl = (L.downloads || "{n}").replace("{n}", it.download_count);
    return '<div class="card lib-card">' +
      '<div class="lib-meta"><span class="chip">' + TT.esc(it.category || "—") + "</span>" +
      '<span class="badge badge-approved">' + L.approved + "</span></div>" +
      "<h3>" + TT.esc(it.title) + "</h3>" +
      '<p class="muted small flex-1">' + TT.esc(it.description || "") + "</p>" +
      '<div class="muted small">' + L.by + " " + TT.esc(it.uploader_name || "") + " · " + TT.esc(dl) + "</div>" +
      '<div class="row"><a class="btn btn-primary btn-sm" href="/api/library/' + it.id + '/download">' +
      L.download + "</a>" + saveBtn + "</div></div>";
  }

  async function loadShared() {
    var out = await TT.api("/api/library", "GET");
    var grid = document.getElementById("shared-grid");
    var empty = document.getElementById("shared-empty");
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    grid.innerHTML = out.data.map(sharedCard).join("");
    empty.hidden = out.data.length > 0;
    grid.querySelectorAll("[data-save]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var r = await TT.api("/api/library/" + b.getAttribute("data-save") + "/save", "POST", {});
        TT.toast(r.message, r.success ? "success" : "error");
        if (r.success) loadShared();
      });
    });
  }

  // ---- private space ----
  function privateCard(it) {
    return '<div class="card lib-card">' +
      '<div class="lib-meta"><span class="chip">' + TT.esc(it.category || "—") + "</span></div>" +
      "<h3>" + TT.esc(it.title) + "</h3>" +
      '<div class="row mt-auto">' +
      '<a class="btn btn-primary btn-sm" href="/api/library/private/' + it.private_id + '/download">' + L.download + "</a>" +
      '<button class="btn btn-ghost btn-sm" data-offline="' + it.private_id + '" data-name="' + TT.esc(it.file_name) + '">' +
      L.saveOffline + "</button></div></div>";
  }

  async function loadPrivate() {
    var out = await TT.api("/api/library/mine", "GET");
    var grid = document.getElementById("private-grid");
    var empty = document.getElementById("private-empty");
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    grid.innerHTML = out.data.map(privateCard).join("");
    empty.hidden = out.data.length > 0;
    grid.querySelectorAll("[data-offline]").forEach(function (b) {
      b.addEventListener("click", function () {
        saveOffline(b.getAttribute("data-offline"), b.getAttribute("data-name"), b);
      });
    });
  }

  // ---- IndexedDB offline copies ----
  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open("tt-offline", 1);
      req.onupgradeneeded = function () {
        req.result.createObjectStore("files", { keyPath: "id" });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }
  async function saveOffline(privateId, name, btn) {
    try {
      btn.disabled = true;
      var res = await fetch("/api/library/private/" + privateId + "/download", { credentials: "same-origin" });
      var blob = await res.blob();
      var db = await openDB();
      await new Promise(function (resolve, reject) {
        var tx = db.transaction("files", "readwrite");
        tx.objectStore("files").put({ id: privateId, name: name, mime: blob.type, blob: blob, savedAt: Date.now() });
        tx.oncomplete = resolve; tx.onerror = function () { reject(tx.error); };
      });
      TT.toast(L.saveOfflineOk, "success");
    } catch (e) {
      TT.toast(L.generic, "error");
      btn.disabled = false;
    }
  }

  // ---- upload ----
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-tab]").forEach(function (b) {
      b.addEventListener("click", function () { switchTab(b.getAttribute("data-tab")); });
    });
    var form = document.getElementById("lib-upload-form");
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var errBox = form.querySelector(".form-error");
      errBox.hidden = true;
      var fd = new FormData(form);
      var btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        var out = await TT.upload("/api/library/submit", fd);
        if (out.success) { TT.toast(out.message, "success"); form.reset(); switchTab("shared"); }
        else { errBox.textContent = out.message; errBox.hidden = false; }
      } catch (e) { errBox.textContent = L.generic; errBox.hidden = false; }
      finally { btn.disabled = false; }
    });
    loadShared();
  });
})();
